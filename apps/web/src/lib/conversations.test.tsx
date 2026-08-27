import { act, renderHook, waitFor } from "@testing-library/react";
import {
  focusManager,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Message, MessagePage } from "./api";
import {
  createMessageAttempt,
  mergeMessagePages,
  messageKey,
  unreadKey,
  useConversation,
  useUnreadCounts,
} from "./conversations";
import { workspaceKey } from "./workspaces";

function message(id: string, createdAt: string): Message {
  return {
    id,
    client_message_id: "11111111-1111-4111-8111-111111111111",
    message_type: "text",
    body: id,
    attachment: null,
    sender: {
      id: "22222222-2222-4222-8222-222222222222",
      full_name: "Pengirim",
    },
    read_at: null,
    created_at: createdAt,
  };
}

function jsonResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve({ data }),
  };
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  readonly url: string;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  open() {
    this.onopen?.();
  }

  disconnect() {
    this.onclose?.();
  }

  fail() {
    this.onerror?.();
    this.onclose?.();
  }

  receive(value: unknown) {
    this.onmessage?.({ data: JSON.stringify(value) } as MessageEvent<string>);
  }
}

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
  vi.stubGlobal("location", { protocol: "https:", host: "jepret.test" });
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  focusManager.setFocused(undefined);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("message pagination", () => {
  it("merges keyset pages by message id without changing chronological order", () => {
    const pages: MessagePage[] = [
      {
        items: [
          message("one", "2026-08-25T01:00:00Z"),
          message("two", "2026-08-25T02:00:00Z"),
        ],
        next_cursor: "cursor-2",
      },
      {
        items: [
          message("two", "2026-08-25T02:00:00Z"),
          message("three", "2026-08-25T03:00:00Z"),
        ],
        next_cursor: null,
      },
    ];

    expect(mergeMessagePages(pages).map(({ id }) => id)).toEqual([
      "one",
      "two",
      "three",
    ]);
  });

  it("uses lexical message id as the canonical timestamp tie-breaker", () => {
    const createdAt = "2026-08-25T01:00:00Z";
    expect(
      mergeMessagePages([
        {
          items: [
            message("z-message", createdAt),
            message("a-message", createdAt),
          ],
          next_cursor: null,
        },
      ]).map(({ id }) => id),
    ).toEqual(["a-message", "z-message"]);
  });

  it("requests the next page with the server cursor", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          items: [message("one", "2026-08-25T01:00:00Z")],
          next_cursor: "cursor-1",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          items: [message("two", "2026-08-25T02:00:00Z")],
          next_cursor: null,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { wrapper } = setup();
    const { result } = renderHook(() => useConversation("conversation-1"), {
      wrapper,
    });

    await waitFor(() => expect(result.current.query.isSuccess).toBe(true));
    await result.current.query.fetchNextPage();

    await waitFor(() =>
      expect(result.current.messages.map(({ id }) => id)).toEqual([
        "one",
        "two",
      ]),
    );

    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/conversations/conversation-1/messages?cursor=cursor-1",
      expect.anything(),
    );
  });

  it("keeps canonical chronology when realtime arrives before the next page", async () => {
    const firstId = "00000000-0000-4000-8000-000000000001";
    const middleId = "00000000-0000-4000-8000-000000000002";
    const newestId = "00000000-0000-4000-8000-000000000003";
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          items: [message(firstId, "2026-08-25T01:00:00Z")],
          next_cursor: "cursor-1",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          items: [message(middleId, "2026-08-25T02:00:00Z")],
          next_cursor: null,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { wrapper } = setup();
    const { result } = renderHook(() => useConversation("conversation-1"), {
      wrapper,
    });
    await waitFor(() => expect(result.current.query.isSuccess).toBe(true));

    act(() => {
      FakeWebSocket.instances[0].receive({
        type: "message.created",
        data: message(newestId, "2026-08-25T03:00:00Z"),
      });
    });
    await result.current.query.fetchNextPage();

    await waitFor(() =>
      expect(result.current.messages.map(({ id }) => id)).toEqual([
        firstId,
        middleId,
        newestId,
      ]),
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("message mutations", () => {
  it("keeps one client_message_id across an automatic request retry", async () => {
    const sentBodies: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      sentBodies.push(JSON.parse(String(init.body)) as Record<string, unknown>);
      if (sentBodies.length === 1) throw new TypeError("network");
      return jsonResponse(message("server-1", "2026-08-25T01:00:00Z"), 201);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { wrapper } = setup();
    const { result } = renderHook(() => useConversation("conversation-1"), {
      wrapper,
    });
    const attempt = createMessageAttempt(
      { message_type: "text", body: "Halo" },
      () => "stable-message-id",
    );

    await act(() => result.current.sendMessage.mutateAsync(attempt));

    expect(sentBodies).toHaveLength(2);
    expect(sentBodies.map((body) => body.client_message_id)).toEqual([
      "stable-message-id",
      "stable-message-id",
    ]);
    expect(sentBodies[1]).toEqual({
      client_message_id: "stable-message-id",
      message_type: "text",
      body: "Halo",
      upload_id: null,
    });
  });

  it("creates the attachment discriminant without a text body", () => {
    expect(
      createMessageAttempt(
        { message_type: "attachment", upload_id: "upload-1" },
        () => "attachment-message-id",
      ),
    ).toEqual({
      client_message_id: "attachment-message-id",
      message_type: "attachment",
      body: null,
      upload_id: "upload-1",
    });
  });

  it("orders reversed concurrent send completions canonically", async () => {
    const sendResolvers = new Map<
      string,
      (value: ReturnType<typeof jsonResponse>) => void
    >();
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      if (!init?.body) {
        return Promise.resolve(jsonResponse({ items: [], next_cursor: null }));
      }
      const body = JSON.parse(String(init.body)) as {
        client_message_id: string;
      };
      return new Promise<ReturnType<typeof jsonResponse>>((resolve) => {
        sendResolvers.set(body.client_message_id, resolve);
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const { wrapper } = setup();
    const { result } = renderHook(() => useConversation("conversation-1"), {
      wrapper,
    });
    await waitFor(() => expect(result.current.query.isSuccess).toBe(true));
    const firstId = "10000000-0000-4000-8000-000000000001";
    const secondId = "20000000-0000-4000-8000-000000000002";
    const first = createMessageAttempt(
      { message_type: "text", body: "Pertama" },
      () => firstId,
    );
    const second = createMessageAttempt(
      { message_type: "text", body: "Kedua" },
      () => secondId,
    );

    const firstPromise = result.current.sendMessage.mutateAsync(first);
    const secondPromise = result.current.sendMessage.mutateAsync(second);
    await waitFor(() => expect(sendResolvers.size).toBe(2));
    sendResolvers.get(secondId)?.(
      jsonResponse(message(secondId, "2026-08-25T02:00:00Z"), 201),
    );
    sendResolvers.get(firstId)?.(
      jsonResponse(message(firstId, "2026-08-25T01:00:00Z"), 201),
    );
    await Promise.all([firstPromise, secondPromise]);

    await waitFor(() =>
      expect(result.current.messages.map(({ id }) => id)).toEqual([
        firstId,
        secondId,
      ]),
    );
  });
});

describe("unread counts", () => {
  it("keeps the non-paginated API response as a flat query value", async () => {
    const counts = [{ booking_id: "booking-1", count: 2 }];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(counts)));
    const { wrapper } = setup();
    const { result } = renderHook(() => useUnreadCounts(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(counts);
  });
});

describe("conversation realtime fallback", () => {
  it("uses the same-origin websocket URL and merges only validated message events", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ items: [], next_cursor: null })),
    );
    const { client, wrapper } = setup();
    const { result } = renderHook(
      () => useConversation("conversation-1", "booking-1"),
      { wrapper },
    );
    await waitFor(() => expect(result.current.query.isSuccess).toBe(true));
    const socket = FakeWebSocket.instances[0];
    const messageId = "33333333-3333-4333-8333-333333333333";
    expect(socket.url).toBe(
      "wss://jepret.test/ws/conversations/conversation-1",
    );

    act(() => {
      socket.receive({ type: "message.created", data: { id: "invalid" } });
      socket.receive({
        type: "message.created",
        data: message(messageId, "2026-08-25T04:00:00Z"),
      });
      socket.receive({
        type: "message.created",
        data: message(messageId, "2026-08-25T04:00:00Z"),
      });
    });

    const cached = client.getQueryData<{
      pages: MessagePage[];
      pageParams: unknown[];
    }>(messageKey("conversation-1"));
    expect(mergeMessagePages(cached?.pages ?? []).map(({ id }) => id)).toEqual([
      messageId,
    ]);
  });

  it("rejects malformed or out-of-contract message events", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ items: [], next_cursor: null })),
    );
    const { client, wrapper } = setup();
    const { result } = renderHook(() => useConversation("conversation-1"), {
      wrapper,
    });
    await waitFor(() => expect(result.current.query.isSuccess).toBe(true));
    const socket = FakeWebSocket.instances[0];
    const valid = message(
      "abcdefab-cdef-4abc-8def-abcdefabcdef",
      "2026-08-25T04:00:00Z",
    );

    act(() => {
      socket.receive({
        type: "message.created",
        data: { ...valid, id: valid.id.toUpperCase() },
      });
      socket.receive({
        type: "message.created",
        data: { ...valid, created_at: "August 25, 2026" },
      });
      socket.receive({
        type: "message.created",
        data: { ...valid, created_at: "2026-02-30T04:00:00Z" },
      });
      socket.receive({
        type: "message.created",
        data: { ...valid, body: "x".repeat(2001) },
      });
      socket.receive({
        type: "message.created",
        data: {
          ...valid,
          attachment: {
            id: "44444444-4444-4444-8444-444444444444",
            filename: "x".repeat(256),
            content_type: "image/png",
            size_bytes: 1,
          },
        },
      });
      socket.receive({
        type: "message.created",
        data: {
          ...valid,
          attachment: {
            id: "44444444-4444-4444-8444-444444444444",
            filename: "hasil.png",
            content_type: "x".repeat(101),
            size_bytes: 1,
          },
        },
      });
      socket.receive({
        type: "message.created",
        data: {
          ...valid,
          attachment: {
            id: "44444444-4444-4444-8444-444444444444",
            filename: "hasil.png",
            content_type: "image/png",
            size_bytes: 10 * 1024 * 1024 + 1,
          },
        },
      });
    });

    const cached = client.getQueryData<{
      pages: MessagePage[];
      pageParams: unknown[];
    }>(messageKey("conversation-1"));
    expect(mergeMessagePages(cached?.pages ?? [])).toEqual([]);
  });

  it("keeps a validated live message that arrives before the first page", async () => {
    let resolveFetch!: (value: ReturnType<typeof jsonResponse>) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<ReturnType<typeof jsonResponse>>((resolve) => {
            resolveFetch = resolve;
          }),
      ),
    );
    const { client, wrapper } = setup();
    const { result } = renderHook(() => useConversation("conversation-1"), {
      wrapper,
    });
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));

    act(() => {
      FakeWebSocket.instances[0].receive({
        type: "message.created",
        data: message(
          "55555555-5555-4555-8555-555555555555",
          "2026-08-25T04:00:00Z",
        ),
      });
    });
    resolveFetch(jsonResponse({ items: [], next_cursor: null }));
    await waitFor(() => expect(result.current.query.isSuccess).toBe(true));

    const cached = client.getQueryData<{
      pages: MessagePage[];
      pageParams: unknown[];
    }>(messageKey("conversation-1"));
    expect(mergeMessagePages(cached?.pages ?? []).map(({ id }) => id)).toEqual([
      "55555555-5555-4555-8555-555555555555",
    ]);
  });

  it("invalidates only exact workspace and unread keys for validated events", async () => {
    const bookingId = "66666666-6666-4666-8666-666666666666";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ items: [], next_cursor: null })),
    );
    const { client, wrapper } = setup();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(
      () => useConversation("conversation-1", bookingId),
      { wrapper },
    );
    await waitFor(() => expect(result.current.query.isSuccess).toBe(true));
    const socket = FakeWebSocket.instances[0];

    act(() => {
      socket.receive({ type: "booking.updated", data: { id: 4 } });
      socket.receive({
        type: "deliverable.updated",
        data: { booking_id: bookingId },
      });
      socket.receive({
        type: "message.read",
        data: { count: 1, read_at: "2026-08-25T04:00:00Z" },
      });
      socket.receive({ type: "unknown", data: {} });
    });

    expect(invalidate).toHaveBeenCalledWith({
      queryKey: workspaceKey(bookingId),
      exact: true,
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: unreadKey,
      exact: true,
    });
    expect(invalidate).not.toHaveBeenCalledWith({
      queryKey: workspaceKey("4"),
      exact: true,
    });
  });

  it("polls every five seconds only while disconnected", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ items: [], next_cursor: null }));
    vi.stubGlobal("fetch", fetchMock);
    const { wrapper } = setup();
    const { result } = renderHook(() => useConversation("conversation-1"), {
      wrapper,
    });
    await act(async () => vi.advanceTimersByTimeAsync(0));
    expect(result.current.query.isSuccess).toBe(true);
    const socket = FakeWebSocket.instances[0];

    act(() => socket.open());
    fetchMock.mockClear();
    await act(async () => vi.advanceTimersByTimeAsync(10_000));
    expect(fetchMock).not.toHaveBeenCalled();

    act(() => socket.disconnect());
    await act(async () => vi.advanceTimersByTimeAsync(5_000));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("refetches after reconnect and on window focus, then cleans up", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ items: [], next_cursor: null }));
    vi.stubGlobal("fetch", fetchMock);
    const { wrapper } = setup();
    const { result, unmount } = renderHook(
      () => useConversation("conversation-1"),
      { wrapper },
    );
    await act(async () => vi.advanceTimersByTimeAsync(0));
    expect(result.current.query.isSuccess).toBe(true);
    const first = FakeWebSocket.instances[0];
    act(() => first.open());
    fetchMock.mockClear();

    act(() => first.disconnect());
    await act(async () => vi.advanceTimersByTimeAsync(1_000));
    const second = FakeWebSocket.instances[1];
    act(() => second.open());
    await act(async () => vi.advanceTimersByTimeAsync(0));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fetchMock.mockClear();
    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });
    await act(async () => vi.advanceTimersByTimeAsync(0));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    unmount();
    expect(second.close).toHaveBeenCalledTimes(1);
    await act(async () => vi.advanceTimersByTimeAsync(60_000));
    expect(FakeWebSocket.instances).toHaveLength(2);
    focusManager.setFocused(undefined);
  });

  it("refetches when the first socket fails before it ever opens", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: [], next_cursor: null }))
      .mockResolvedValue(
        jsonResponse({
          items: [message("recovered", "2026-08-25T05:00:00Z")],
          next_cursor: null,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { wrapper } = setup();
    const { result, unmount } = renderHook(
      () => useConversation("conversation-1", "booking-1"),
      { wrapper },
    );
    await act(async () => vi.advanceTimersByTimeAsync(0));
    expect(result.current.query.isSuccess).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    act(() => FakeWebSocket.instances[0].fail());
    await act(async () => vi.advanceTimersByTimeAsync(999));
    expect(FakeWebSocket.instances).toHaveLength(1);
    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(FakeWebSocket.instances).toHaveLength(2);

    act(() => FakeWebSocket.instances[1].open());
    await act(async () => vi.advanceTimersByTimeAsync(0));

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.current.messages.map(({ id }) => id)).toEqual(["recovered"]);
    expect(result.current.connected).toBe(true);

    await act(async () => vi.advanceTimersByTimeAsync(10_000));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(FakeWebSocket.instances).toHaveLength(2);

    unmount();
    await act(async () => vi.advanceTimersByTimeAsync(60_000));
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("resumes fallback polling when switching to a stalled conversation", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ items: [], next_cursor: null }));
    vi.stubGlobal("fetch", fetchMock);
    const { wrapper } = setup();
    const { result, rerender, unmount } = renderHook(
      ({ conversationId, bookingId }) =>
        useConversation(conversationId, bookingId),
      {
        wrapper,
        initialProps: {
          conversationId: "conversation-a",
          bookingId: "booking-a",
        },
      },
    );
    await act(async () => vi.advanceTimersByTimeAsync(0));
    expect(result.current.query.isSuccess).toBe(true);
    const oldSocket = FakeWebSocket.instances[0];
    act(() => oldSocket.open());
    expect(result.current.connected).toBe(true);

    rerender({ conversationId: "conversation-b", bookingId: "booking-b" });
    await act(async () => vi.advanceTimersByTimeAsync(0));
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(result.current.connected).toBe(false);
    const callsBeforePolling = fetchMock.mock.calls.length;

    act(() => {
      oldSocket.open();
      oldSocket.disconnect();
    });
    await act(async () => vi.advanceTimersByTimeAsync(5_000));
    expect(fetchMock).toHaveBeenCalledTimes(callsBeforePolling + 1);
    expect(FakeWebSocket.instances).toHaveLength(2);

    unmount();
  });

  it("does not merge an in-flight message from the previous conversation", async () => {
    let resolveOldFetch!: (value: ReturnType<typeof jsonResponse>) => void;
    const fetchMock = vi.fn((url: string) => {
      if (url.includes("conversation-a")) {
        return new Promise<ReturnType<typeof jsonResponse>>((resolve) => {
          resolveOldFetch = resolve;
        });
      }
      return Promise.resolve(jsonResponse({ items: [], next_cursor: null }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const { wrapper } = setup();
    const { result, rerender } = renderHook(
      ({ conversationId }) => useConversation(conversationId),
      { wrapper, initialProps: { conversationId: "conversation-a" } },
    );
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    act(() => {
      FakeWebSocket.instances[0].receive({
        type: "message.created",
        data: message(
          "77777777-7777-4777-8777-777777777777",
          "2026-08-25T04:00:00Z",
        ),
      });
    });

    rerender({ conversationId: "conversation-b" });
    await waitFor(() => expect(result.current.query.isSuccess).toBe(true));

    expect(result.current.messages).toEqual([]);
    await act(async () => {
      resolveOldFetch(jsonResponse({ items: [], next_cursor: null }));
      await Promise.resolve();
    });
  });

  it("isolates StrictMode cleanup from the current socket generation", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ items: [], next_cursor: null })),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const firstHook = renderHook(() => useConversation("conversation-1"), {
      wrapper,
    });
    await act(async () => vi.advanceTimersByTimeAsync(0));
    const stale = FakeWebSocket.instances[0];
    firstHook.unmount();

    const currentHook = renderHook(() => useConversation("conversation-1"), {
      wrapper,
    });
    await act(async () => vi.advanceTimersByTimeAsync(0));
    expect(FakeWebSocket.instances).toHaveLength(2);
    const current = FakeWebSocket.instances[1];

    act(() => {
      stale.open();
      stale.disconnect();
      current.open();
    });
    expect(currentHook.result.current.connected).toBe(true);
    await act(async () => vi.advanceTimersByTimeAsync(5_000));
    expect(FakeWebSocket.instances).toHaveLength(2);

    currentHook.unmount();
    expect(current.close).toHaveBeenCalledTimes(1);
  });
});
