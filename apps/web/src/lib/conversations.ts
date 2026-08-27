"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { apiFetch, type Message, type MessagePage } from "./api";
import { workspaceKey } from "./workspaces";

export const messageKey = (conversationId: string) =>
  ["conversations", conversationId, "messages"] as const;
export const unreadKey = ["conversations", "unread"] as const;

export type SendMessageInput =
  | { message_type: "text"; body: string }
  | { message_type: "attachment"; upload_id: string };

export type SendMessageAttempt =
  | {
      client_message_id: string;
      message_type: "text";
      body: string;
      upload_id: null;
    }
  | {
      client_message_id: string;
      message_type: "attachment";
      body: null;
      upload_id: string;
    };

export interface ReadReceipt {
  count: number;
  read_at: string;
}

export interface UnreadCount {
  booking_id: string;
  count: number;
}

export function createMessageAttempt(
  input: SendMessageInput,
  createId: () => string = () => globalThis.crypto.randomUUID(),
): SendMessageAttempt {
  const clientMessageId = createId();
  return input.message_type === "text"
    ? {
        client_message_id: clientMessageId,
        message_type: "text",
        body: input.body,
        upload_id: null,
      }
    : {
        client_message_id: clientMessageId,
        message_type: "attachment",
        body: null,
        upload_id: input.upload_id,
      };
}

export function mergeMessagePages(pages: readonly MessagePage[]): Message[] {
  const byId = new Map<string, Message>();
  for (const page of pages) {
    for (const item of page.items) {
      if (!byId.has(item.id)) byId.set(item.id, item);
    }
  }
  return [...byId.values()].sort((left, right) => {
    const timestampDifference =
      Date.parse(left.created_at) - Date.parse(right.created_at);
    if (timestampDifference !== 0) return timestampDifference;
    return left.id < right.id ? -1 : left.id > right.id ? 1 : 0;
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableString(value: unknown): value is string | null {
  return typeof value === "string" || value === null;
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const ISO_DATETIME_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(?:Z|([+-])(\d{2}):(\d{2}))$/;
const MAX_CHAT_ATTACHMENT_SIZE = 10 * 1024 * 1024;

function isCanonicalUuid(value: unknown): value is string {
  return typeof value === "string" && UUID_PATTERN.test(value);
}

function isCanonicalDate(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = ISO_DATETIME_PATTERN.exec(value);
  if (!match) return false;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText] =
    match;
  const [year, month, day, hour, minute, second] = [
    yearText,
    monthText,
    dayText,
    hourText,
    minuteText,
    secondText,
  ].map(Number);
  const offsetHour = match[8] ? Number(match[8]) : 0;
  const offsetMinute = match[9] ? Number(match[9]) : 0;
  const calendar = new Date(0);
  calendar.setUTCFullYear(year, month - 1, day);
  calendar.setUTCHours(hour, minute, second, 0);
  return (
    year >= 1 &&
    month >= 1 &&
    month <= 12 &&
    day >= 1 &&
    hour <= 23 &&
    minute <= 59 &&
    second <= 59 &&
    offsetHour <= 23 &&
    offsetMinute <= 59 &&
    calendar.getUTCFullYear() === year &&
    calendar.getUTCMonth() === month - 1 &&
    calendar.getUTCDate() === day &&
    Number.isFinite(Date.parse(value))
  );
}

function isBoundedString(
  value: unknown,
  maxLength: number,
  minLength = 0,
): value is string {
  if (typeof value !== "string") return false;
  const length = Array.from(value).length;
  return length >= minLength && length <= maxLength;
}

function isMessage(value: unknown): value is Message {
  if (!isRecord(value) || !isRecord(value.sender)) return false;
  const attachment = value.attachment;
  const attachmentValid =
    attachment === null ||
    (isRecord(attachment) &&
      isCanonicalUuid(attachment.id) &&
      isBoundedString(attachment.filename, 255, 1) &&
      isBoundedString(attachment.content_type, 100, 1) &&
      typeof attachment.size_bytes === "number" &&
      Number.isFinite(attachment.size_bytes) &&
      Number.isInteger(attachment.size_bytes) &&
      attachment.size_bytes > 0 &&
      attachment.size_bytes <= MAX_CHAT_ATTACHMENT_SIZE);
  return (
    isCanonicalUuid(value.id) &&
    isCanonicalUuid(value.client_message_id) &&
    ["text", "attachment", "system"].includes(String(value.message_type)) &&
    isNullableString(value.body) &&
    (value.body === null || isBoundedString(value.body, 2000)) &&
    attachmentValid &&
    isCanonicalUuid(value.sender.id) &&
    isBoundedString(value.sender.full_name, 100, 1) &&
    (value.read_at === null || isCanonicalDate(value.read_at)) &&
    isCanonicalDate(value.created_at)
  );
}

function appendMessage(
  current: InfiniteData<MessagePage, string | null> | undefined,
  incoming: Message,
): InfiniteData<MessagePage, string | null> {
  if (!current) {
    return {
      pages: [{ items: [incoming], next_cursor: null }],
      pageParams: [null],
    };
  }
  if (
    current.pages.some((page) =>
      page.items.some(({ id }) => id === incoming.id),
    )
  ) {
    return current;
  }
  const lastIndex = current.pages.length - 1;
  if (lastIndex < 0) {
    return {
      pages: [{ items: [incoming], next_cursor: null }],
      pageParams: [null],
    };
  }
  return {
    ...current,
    pages: current.pages.map((page, index) =>
      index === lastIndex
        ? { ...page, items: [...page.items, incoming] }
        : page,
    ),
  };
}

type KnownEvent =
  | { type: "message.created"; data: Message }
  | { type: "message.read"; data: ReadReceipt }
  | { type: "booking.updated"; data: { id: string } }
  | { type: "deliverable.updated"; data: { booking_id: string } }
  | { type: "pong" };

function parseEvent(raw: unknown): KnownEvent | null {
  if (typeof raw !== "string") return null;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(value) || typeof value.type !== "string") return null;
  if (value.type === "pong") return { type: "pong" };
  if (value.type === "message.created" && isMessage(value.data)) {
    return { type: value.type, data: value.data };
  }
  if (value.type === "message.read" && isRecord(value.data)) {
    if (
      typeof value.data.count === "number" &&
      Number.isFinite(value.data.count) &&
      Number.isInteger(value.data.count) &&
      value.data.count >= 0 &&
      isCanonicalDate(value.data.read_at)
    ) {
      return {
        type: value.type,
        data: { count: value.data.count, read_at: value.data.read_at },
      };
    }
    return null;
  }
  if (
    value.type === "booking.updated" &&
    isRecord(value.data) &&
    isCanonicalUuid(value.data.id)
  ) {
    return { type: value.type, data: { id: value.data.id } };
  }
  if (
    value.type === "deliverable.updated" &&
    isRecord(value.data) &&
    isCanonicalUuid(value.data.booking_id)
  ) {
    return { type: value.type, data: { booking_id: value.data.booking_id } };
  }
  return null;
}

function messagePath(conversationId: string, cursor: string | null): string {
  const base = `/conversations/${conversationId}/messages`;
  return cursor ? `${base}?cursor=${encodeURIComponent(cursor)}` : base;
}

export function useUnreadCounts() {
  return useQuery({
    queryKey: unreadKey,
    queryFn: () => apiFetch<UnreadCount[]>("/conversations/unread"),
  });
}

export function useConversation(conversationId: string, bookingId?: string) {
  const queryClient = useQueryClient();
  const connectionKey = JSON.stringify([conversationId, bookingId ?? null]);
  const [connectionState, setConnectionState] = useState(() => ({
    key: connectionKey,
    connected: false,
  }));
  const connected =
    connectionState.key === connectionKey && connectionState.connected;
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<{
    generation: number;
    timer: ReturnType<typeof setTimeout>;
  } | null>(null);
  const reconnectAttemptRef = useRef(0);
  const needsRefetchOnOpenRef = useRef(false);
  const pendingMessagesRef = useRef(new Map<string, Map<string, Message>>());
  const generationRef = useRef(0);

  const query = useInfiniteQuery({
    queryKey: messageKey(conversationId),
    queryFn: async ({ pageParam }) => {
      const page = await apiFetch<MessagePage>(
        messagePath(conversationId, pageParam),
      );
      const pendingForConversation =
        pendingMessagesRef.current.get(conversationId);
      if (
        pageParam !== null ||
        !pendingForConversation ||
        pendingForConversation.size === 0
      ) {
        return page;
      }
      const pending = [...pendingForConversation.values()];
      pendingMessagesRef.current.delete(conversationId);
      return {
        ...page,
        items: mergeMessagePages([page, { items: pending, next_cursor: null }]),
      };
    },
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    refetchInterval: connected ? false : 5_000,
    refetchOnWindowFocus: true,
    retry: false,
  });

  useEffect(() => {
    if (typeof window === "undefined" || typeof WebSocket === "undefined")
      return;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    reconnectAttemptRef.current = 0;
    for (const pendingConversationId of pendingMessagesRef.current.keys()) {
      if (pendingConversationId !== conversationId) {
        pendingMessagesRef.current.delete(pendingConversationId);
      }
    }
    let active = true;
    const ownedSockets = new Set<WebSocket>();

    const isCurrent = () => active && generationRef.current === generation;
    const setGenerationConnected = (value: boolean) => {
      setConnectionState((current) =>
        current.key === connectionKey && current.connected === value
          ? current
          : { key: connectionKey, connected: value },
      );
    };

    const clearReconnect = () => {
      if (reconnectTimerRef.current?.generation === generation) {
        clearTimeout(reconnectTimerRef.current.timer);
        reconnectTimerRef.current = null;
      }
    };

    const connect = () => {
      if (!isCurrent()) return;
      clearReconnect();
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const socket = new WebSocket(
        `${protocol}//${window.location.host}/ws/conversations/${conversationId}`,
      );
      ownedSockets.add(socket);
      socketRef.current = socket;

      socket.onopen = () => {
        if (!isCurrent() || socketRef.current !== socket) return;
        const needsRefetch = needsRefetchOnOpenRef.current;
        needsRefetchOnOpenRef.current = false;
        reconnectAttemptRef.current = 0;
        if (needsRefetch) {
          void queryClient.refetchQueries({
            queryKey: messageKey(conversationId),
            exact: true,
          });
          void queryClient.invalidateQueries({
            queryKey: unreadKey,
            exact: true,
          });
          if (bookingId) {
            void queryClient.invalidateQueries({
              queryKey: workspaceKey(bookingId),
              exact: true,
            });
          }
        }
        setGenerationConnected(true);
      };
      socket.onmessage = (event) => {
        if (!isCurrent() || socketRef.current !== socket) return;
        const parsed = parseEvent(event.data);
        if (!parsed || parsed.type === "pong") return;
        if (parsed.type === "message.created") {
          if (
            queryClient.getQueryState(messageKey(conversationId))
              ?.fetchStatus === "fetching"
          ) {
            const pendingForConversation =
              pendingMessagesRef.current.get(conversationId) ??
              new Map<string, Message>();
            pendingForConversation.set(parsed.data.id, parsed.data);
            pendingMessagesRef.current.set(
              conversationId,
              pendingForConversation,
            );
          }
          queryClient.setQueryData<InfiniteData<MessagePage, string | null>>(
            messageKey(conversationId),
            (current) => appendMessage(current, parsed.data),
          );
          void queryClient.invalidateQueries({
            queryKey: unreadKey,
            exact: true,
          });
          if (bookingId) {
            void queryClient.invalidateQueries({
              queryKey: workspaceKey(bookingId),
              exact: true,
            });
          }
          return;
        }
        if (parsed.type === "message.read") {
          void queryClient.invalidateQueries({
            queryKey: messageKey(conversationId),
            exact: true,
          });
          void queryClient.invalidateQueries({
            queryKey: unreadKey,
            exact: true,
          });
          if (bookingId) {
            void queryClient.invalidateQueries({
              queryKey: workspaceKey(bookingId),
              exact: true,
            });
          }
          return;
        }
        const eventBookingId =
          parsed.type === "booking.updated"
            ? parsed.data.id
            : parsed.data.booking_id;
        void queryClient.invalidateQueries({
          queryKey: workspaceKey(eventBookingId),
          exact: true,
        });
      };
      socket.onerror = () => {
        if (!isCurrent() || socketRef.current !== socket) return;
        needsRefetchOnOpenRef.current = true;
        setGenerationConnected(false);
        try {
          socket.close();
        } catch {
          // Polling remains active even if the browser cannot close the socket.
        }
      };
      socket.onclose = () => {
        if (!isCurrent() || socketRef.current !== socket) return;
        ownedSockets.delete(socket);
        needsRefetchOnOpenRef.current = true;
        socketRef.current = null;
        setGenerationConnected(false);
        const attempt = reconnectAttemptRef.current;
        reconnectAttemptRef.current += 1;
        const delay = Math.min(1_000 * 2 ** attempt, 30_000);
        reconnectTimerRef.current = {
          generation,
          timer: setTimeout(connect, delay),
        };
      };
    };

    connect();
    return () => {
      active = false;
      clearReconnect();
      for (const socket of ownedSockets) {
        socket.onopen = null;
        socket.onclose = null;
        socket.onerror = null;
        socket.onmessage = null;
        socket.close();
      }
      ownedSockets.clear();
      if (generationRef.current === generation) socketRef.current = null;
    };
  }, [bookingId, connectionKey, conversationId, queryClient]);

  const sendMessage = useMutation({
    mutationFn: (attempt: SendMessageAttempt) =>
      apiFetch<Message>(`/conversations/${conversationId}/messages`, {
        method: "POST",
        body: JSON.stringify(attempt),
      }),
    retry: 1,
    onSuccess: (sent) => {
      queryClient.setQueryData<InfiniteData<MessagePage, string | null>>(
        messageKey(conversationId),
        (current) => appendMessage(current, sent),
      );
    },
  });

  const markRead = useMutation({
    mutationFn: () =>
      apiFetch<ReadReceipt>(`/conversations/${conversationId}/read`, {
        method: "POST",
      }),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: unreadKey, exact: true }),
        ...(bookingId
          ? [
              queryClient.invalidateQueries({
                queryKey: workspaceKey(bookingId),
                exact: true,
              }),
            ]
          : []),
      ]),
  });

  const messages = useMemo(
    () => mergeMessagePages(query.data?.pages ?? []),
    [query.data?.pages],
  );

  return { query, messages, connected, sendMessage, markRead };
}
