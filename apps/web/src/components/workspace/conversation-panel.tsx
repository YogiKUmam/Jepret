"use client";

import { useEffect, useRef, useState } from "react";

import type { Upload } from "@/lib/api";
import {
  createMessageAttempt,
  useConversation,
  type SendMessageAttempt,
} from "@/lib/conversations";
import { requestPrivateDownload } from "@/lib/deliverables";
import { UploadField } from "./upload-field";

function formatMessageTime(isoString: string) {
  try {
    return new Intl.DateTimeFormat("id-ID", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Asia/Jakarta",
    }).format(new Date(isoString));
  } catch {
    return "";
  }
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export interface ConversationPanelProps {
  conversationId: string;
  bookingId: string;
  currentUserId: string;
  isReadOnly?: boolean;
}

export function ConversationPanel({
  conversationId,
  bookingId,
  currentUserId,
  isReadOnly = false,
}: ConversationPanelProps) {
  const { messages, connected, sendMessage, markRead, query } = useConversation(
    conversationId,
    bookingId,
  );

  const [text, setText] = useState("");
  const [pendingUpload, setPendingUpload] = useState<Upload | null>(null);
  const [activeAttempt, setActiveAttempt] = useState<SendMessageAttempt | null>(
    null,
  );
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Auto mark read on mount and when unread messages from other user arrive
  const markReadMutate = markRead.mutate;
  useEffect(() => {
    const hasUnread = messages.some(
      (m) => m.sender.id !== currentUserId && m.read_at === null,
    );
    if (hasUnread) {
      markReadMutate();
    }
  }, [conversationId, messages, currentUserId, markReadMutate]);

  // Scroll to bottom on new messages
  useEffect(() => {
    if (typeof messagesEndRef.current?.scrollIntoView === "function") {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages.length]);

  const handleSendText = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || sendMessage.isPending) return;

    const attempt =
      activeAttempt && activeAttempt.message_type === "text"
        ? activeAttempt
        : createMessageAttempt({ message_type: "text", body: trimmed });

    setActiveAttempt(attempt);

    try {
      await sendMessage.mutateAsync(attempt);
      setText("");
      setActiveAttempt(null);
    } catch {
      // Keep activeAttempt so retry preserves same client_message_id
    }
  };

  const handleSendAttachment = async (upload: Upload) => {
    const attempt = createMessageAttempt({
      message_type: "attachment",
      upload_id: upload.id,
    });
    setActiveAttempt(attempt);

    try {
      await sendMessage.mutateAsync(attempt);
      setPendingUpload(null);
      setActiveAttempt(null);
    } catch {
      setPendingUpload(upload);
    }
  };

  const handleDownloadAttachment = async (uploadId: string) => {
    setDownloadingId(uploadId);
    try {
      const { url } = await requestPrivateDownload(uploadId);
      if (typeof window !== "undefined") {
        window.open(url, "_blank", "noopener,noreferrer");
      }
    } catch {
      // ignore or alert
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <div className="flex flex-col rounded-3xl border border-[var(--border)] bg-[var(--background)] p-4 text-[var(--foreground)] sm:p-6">
      {/* Realtime status banner */}
      <div role="status" aria-live="polite" className="sr-only">
        {connected
          ? "Terhubung ke percakapan."
          : "Koneksi terputus, memperbarui berkala…"}
      </div>

      {!connected ? (
        <div
          role="status"
          aria-live="polite"
          className="mb-4 rounded-xl bg-amber-500/10 px-4 py-2 text-xs font-medium text-amber-600 dark:text-amber-400"
        >
          Koneksi percakapan sedang diperbarui secara otomatis.
        </div>
      ) : null}

      {/* Message List */}
      <div className="min-h-[350px] max-h-[500px] flex-1 overflow-y-auto space-y-4 pr-1">
        {query.isPending ? (
          <div aria-hidden className="space-y-3 p-4">
            <div className="h-10 w-2/3 animate-pulse rounded-2xl bg-[var(--border)]" />
            <div className="ml-auto h-10 w-1/2 animate-pulse rounded-2xl bg-[var(--border)]" />
          </div>
        ) : messages.length === 0 ? (
          <div className="flex h-48 items-center justify-center text-center text-sm text-[var(--muted)]">
            Belum ada pesan. Mulai percakapan mengenai jadwal dan detail
            pemotretan.
          </div>
        ) : (
          <ul className="list-none space-y-3 p-0 m-0">
            {messages.map((msg) => {
              const isSelf = msg.sender.id === currentUserId;
              return (
                <li
                  key={msg.id}
                  className={`flex flex-col ${isSelf ? "items-end" : "items-start"}`}
                >
                  <span className="text-[11px] text-[var(--muted)] px-1">
                    {msg.sender.full_name} · {formatMessageTime(msg.created_at)}
                  </span>
                  <div
                    className={`mt-1 max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
                      isSelf
                        ? "bg-[var(--primary)] text-[var(--primary-foreground)] rounded-tr-sm"
                        : "bg-[var(--surface)] text-[var(--surface-foreground)] border border-[var(--border)] rounded-tl-sm"
                    }`}
                  >
                    {msg.message_type === "text" && msg.body ? (
                      <p className="whitespace-pre-wrap break-words">
                        {msg.body}
                      </p>
                    ) : null}

                    {msg.attachment ? (
                      <div className="flex items-center gap-3">
                        <div>
                          <p className="font-medium truncate max-w-[200px]">
                            {msg.attachment.filename}
                          </p>
                          <p className="text-xs opacity-75">
                            {formatBytes(msg.attachment.size_bytes)}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            handleDownloadAttachment(msg.attachment!.id)
                          }
                          disabled={downloadingId === msg.attachment.id}
                          className="inline-flex min-h-9 items-center justify-center rounded-lg border border-current/30 px-2.5 text-xs font-medium transition active:scale-[0.98]"
                        >
                          {downloadingId === msg.attachment.id
                            ? "Memuat…"
                            : "Unduh"}
                        </button>
                      </div>
                    ) : null}
                  </div>
                </li>
              );
            })}
            <div ref={messagesEndRef} />
          </ul>
        )}
      </div>

      {/* Composer */}
      {!isReadOnly ? (
        <div className="mt-4 border-t border-[var(--border)] pt-4">
          {sendMessage.isError ? (
            <p role="alert" className="mb-2 text-xs text-red-500">
              Pesan belum terkirim. Klik tombol kirim lagi untuk mencoba ulang.
            </p>
          ) : null}

          <form onSubmit={handleSendText} className="space-y-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Tulis pesan…"
                maxLength={2000}
                disabled={sendMessage.isPending}
                className="min-h-11 flex-1 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 text-sm text-[var(--surface-foreground)] placeholder-[var(--muted)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
              />
              <button
                type="submit"
                disabled={!text.trim() || sendMessage.isPending}
                className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[var(--primary)] px-5 text-sm font-medium text-[var(--primary-foreground)] shadow-sm transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {sendMessage.isPending ? "Mengirim…" : "Kirim pesan"}
              </button>
            </div>

            <div className="flex items-center justify-between gap-2 pt-1">
              <div className="flex-1">
                <UploadField
                  bookingId={bookingId}
                  purpose="chat_attachment"
                  label="Lampirkan berkas"
                  disabled={sendMessage.isPending}
                  onUploaded={(upload) => void handleSendAttachment(upload)}
                />
              </div>

              {pendingUpload ? (
                <button
                  type="button"
                  onClick={() => void handleSendAttachment(pendingUpload)}
                  className="inline-flex min-h-9 items-center justify-center rounded-lg bg-[var(--primary)] px-3 text-xs font-medium text-[var(--primary-foreground)]"
                >
                  Kirim lampiran
                </button>
              ) : null}
            </div>
          </form>
        </div>
      ) : (
        <p className="mt-4 border-t border-[var(--border)] pt-4 text-center text-xs text-[var(--muted)]">
          Percakapan telah selesai.
        </p>
      )}
    </div>
  );
}
