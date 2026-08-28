"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { DisputeBanner } from "@/components/disputes/dispute-banner";
import { DisputeModal } from "@/components/disputes/dispute-modal";
import { AppHeader } from "@/components/layout/app-header";
import { BottomNavigation } from "@/components/layout/bottom-navigation";
import { ReviewForm } from "@/components/reviews/review-form";
import { ConversationPanel } from "@/components/workspace/conversation-panel";
import { DeliverablesPanel } from "@/components/workspace/deliverables-panel";
import { WorkspaceHeader } from "@/components/workspace/workspace-header";
import type { Dispute, Review } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { getBookingDispute } from "@/lib/disputes";
import { getBookingReview } from "@/lib/reviews";
import { useWorkspace, useWorkspaceAction } from "@/lib/workspaces";

export default function WorkspacePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const bookingId = params.id;

  const { data: me, isPending: mePending } = useMe();
  const workspaceQuery = useWorkspace(bookingId);

  const startAction = useWorkspaceAction(bookingId, "start");
  const deliverAction = useWorkspaceAction(bookingId, "deliver");
  const completeAction = useWorkspaceAction(bookingId, "complete");

  const [activeTab, setActiveTab] = useState<"chat" | "deliverables">("chat");
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [showDisputeModal, setShowDisputeModal] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const [dispute, setDispute] = useState<Dispute | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [loadingExtra, setLoadingExtra] = useState(true);

  const chatTabRef = useRef<HTMLButtonElement | null>(null);
  const deliverablesTabRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!mePending && me === null) {
      router.push("/masuk");
    }
  }, [me, mePending, router]);

  useEffect(() => {
    let isMounted = true;
    if (!bookingId) return;

    Promise.all([
      getBookingDispute(bookingId).catch(() => null),
      getBookingReview(bookingId).catch(() => null),
    ]).then(([disputeData, reviewData]) => {
      if (!isMounted) return;
      setDispute(disputeData);
      setReview(reviewData);
      setLoadingExtra(false);
    });

    return () => {
      isMounted = false;
    };
  }, [bookingId]);

  const workspace = workspaceQuery.data;

  const handleKeyDownTabs = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const nextTab = activeTab === "chat" ? "deliverables" : "chat";
      setActiveTab(nextTab);
      if (nextTab === "chat") chatTabRef.current?.focus();
      else deliverablesTabRef.current?.focus();
    }
  };

  const handleStart = async () => {
    setActionError(null);
    try {
      await startAction.mutateAsync();
    } catch {
      setActionError("Gagal memulai sesi pekerjaan. Silakan coba lagi.");
    }
  };

  const handleDeliver = async () => {
    setActionError(null);
    try {
      await deliverAction.mutateAsync();
    } catch {
      setActionError("Gagal mengirim hasil pekerjaan. Silakan coba lagi.");
    }
  };

  const handleAcceptDelivery = async () => {
    setActionError(null);
    try {
      await completeAction.mutateAsync();
      setShowConfirmModal(false);
    } catch {
      setActionError("Gagal menerima hasil pekerjaan. Silakan coba lagi.");
    }
  };

  if (mePending || workspaceQuery.isPending) {
    return (
      <main className="min-h-screen bg-[var(--surface)] pb-24 text-[var(--surface-foreground)]">
        <AppHeader />
        <section className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
          <div aria-hidden className="space-y-6">
            <div className="h-40 animate-pulse rounded-3xl bg-[var(--border)]" />
            <div className="h-96 animate-pulse rounded-3xl bg-[var(--border)]" />
          </div>
        </section>
        <BottomNavigation />
      </main>
    );
  }

  if (workspaceQuery.isError || !workspace) {
    return (
      <main className="min-h-screen bg-[var(--surface)] pb-24 text-[var(--surface-foreground)]">
        <AppHeader />
        <section className="mx-auto max-w-4xl px-4 py-8 sm:px-6 text-center">
          <div className="rounded-3xl border border-[var(--border)] bg-[var(--background)] p-8">
            <h1 className="font-serif text-2xl font-bold">
              Ruang Kerja Tidak Ditemukan
            </h1>
            <p className="mt-2 text-sm text-[var(--muted)]">
              Ruang kerja booking belum tersedia atau Anda tidak memiliki akses
              ke pesanan ini.
            </p>
            <button
              type="button"
              onClick={() => router.push("/booking")}
              className="mt-6 inline-flex min-h-11 items-center justify-center rounded-xl bg-[var(--primary)] px-6 text-sm font-medium text-[var(--primary-foreground)]"
            >
              Kembali ke Daftar Booking
            </button>
          </div>
        </section>
        <BottomNavigation />
      </main>
    );
  }

  const { booking, conversation, deliverables, role } = workspace;
  const isTerminal =
    booking.status === "completed" || booking.status === "cancelled";

  const canOpenDispute =
    role === "client" &&
    !dispute &&
    ["confirmed", "in_progress", "delivered"].includes(booking.status);

  return (
    <main className="min-h-screen bg-[var(--surface)] pb-24 text-[var(--surface-foreground)]">
      <AppHeader />

      <section className="mx-auto max-w-4xl px-4 py-6 sm:px-6 space-y-6">
        <WorkspaceHeader
          workspace={workspace}
          onStart={handleStart}
          isStarting={startAction.isPending}
          onDeliver={handleDeliver}
          isDelivering={deliverAction.isPending}
          onAccept={() => setShowConfirmModal(true)}
          isAccepting={completeAction.isPending}
          actionError={actionError}
        />

        {/* Dispute Banner if active dispute exists */}
        {dispute && <DisputeBanner dispute={dispute} />}

        {/* Client Review Section when completed */}
        {booking.status === "completed" &&
          role === "client" &&
          !loadingExtra && (
            <div className="space-y-4">
              {review ? (
                <div className="rounded-[28px] border border-white/[0.08] bg-[#1C1C1E]/80 p-6 backdrop-blur-2xl">
                  <div className="flex items-center justify-between">
                    <h3 className="font-serif text-lg font-bold text-[var(--foreground)]">
                      Ulasan Anda untuk Kreator
                    </h3>
                    <span className="text-xs font-semibold text-amber-400">
                      {"★".repeat(review.rating)}{" "}
                      <span className="text-white/20">
                        {"★".repeat(5 - review.rating)}
                      </span>
                    </span>
                  </div>
                  {review.comment && (
                    <p className="mt-2 text-sm text-neutral-300">
                      &ldquo;{review.comment}&rdquo;
                    </p>
                  )}
                </div>
              ) : (
                <ReviewForm
                  bookingId={booking.id}
                  onSuccess={(newReview) => setReview(newReview)}
                />
              )}
            </div>
          )}

        {/* Semantic Tabs with ARIA support */}
        <div
          role="tablist"
          aria-label="Menu Ruang Kerja"
          onKeyDown={handleKeyDownTabs}
          className="flex rounded-2xl border border-[var(--border)] bg-[var(--background)] p-1.5 shadow-xs"
        >
          <button
            ref={chatTabRef}
            id="chat-tab"
            role="tab"
            type="button"
            aria-label="Chat"
            aria-selected={activeTab === "chat"}
            aria-controls="chat-panel"
            tabIndex={activeTab === "chat" ? 0 : -1}
            onClick={() => setActiveTab("chat")}
            className={`flex-1 min-h-11 rounded-xl text-sm font-medium transition ${
              activeTab === "chat"
                ? "bg-[var(--surface)] text-[var(--primary)] font-semibold shadow-xs"
                : "text-[var(--muted)] hover:text-[var(--foreground)]"
            }`}
          >
            Chat
          </button>
          <button
            ref={deliverablesTabRef}
            id="deliverables-tab"
            role="tab"
            type="button"
            aria-label="Hasil"
            aria-selected={activeTab === "deliverables"}
            aria-controls="deliverables-panel"
            tabIndex={activeTab === "deliverables" ? 0 : -1}
            onClick={() => setActiveTab("deliverables")}
            className={`flex-1 min-h-11 rounded-xl text-sm font-medium transition ${
              activeTab === "deliverables"
                ? "bg-[var(--surface)] text-[var(--primary)] font-semibold shadow-xs"
                : "text-[var(--muted)] hover:text-[var(--foreground)]"
            }`}
          >
            Hasil {deliverables.length > 0 ? `(${deliverables.length})` : ""}
          </button>
        </div>

        {/* Tabpanel: Chat */}
        <div
          id="chat-panel"
          role="tabpanel"
          aria-labelledby="chat-tab"
          hidden={activeTab !== "chat"}
        >
          {conversation ? (
            <ConversationPanel
              conversationId={conversation.id}
              bookingId={booking.id}
              currentUserId={me?.id ?? ""}
              isReadOnly={isTerminal}
            />
          ) : (
            <div className="rounded-3xl border border-[var(--border)] bg-[var(--background)] p-8 text-center text-sm text-[var(--muted)]">
              Percakapan belum diinisialisasi.
            </div>
          )}
        </div>

        {/* Tabpanel: Hasil / Deliverables */}
        <div
          id="deliverables-panel"
          role="tabpanel"
          aria-labelledby="deliverables-tab"
          hidden={activeTab !== "deliverables"}
        >
          <DeliverablesPanel
            bookingId={booking.id}
            role={workspace.role}
            status={booking.status}
            deliverables={deliverables}
          />
        </div>

        {/* Client Dispute Button */}
        {canOpenDispute && (
          <div className="pt-2 text-center">
            <button
              type="button"
              onClick={() => setShowDisputeModal(true)}
              className="text-xs font-semibold text-red-400/80 hover:text-red-400 hover:underline active:scale-95"
            >
              Ada masalah dengan pesanan ini? Ajukan Sengketa / Komplain
            </button>
          </div>
        )}
      </section>

      {/* Confirmation Modal for Client Accept Delivery */}
      {showConfirmModal ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-xs"
        >
          <div className="w-full max-w-md rounded-3xl border border-[var(--border)] bg-[var(--background)] p-6 shadow-2xl space-y-4">
            <h2
              id="confirm-modal-title"
              className="font-serif text-xl font-bold"
            >
              Konfirmasi Penerimaan Hasil
            </h2>
            <p className="text-sm text-[var(--muted)] leading-relaxed">
              Apakah Anda sudah puas dengan berkas dan hasil pekerjaan ini?
              Setelah dikonfirmasi, pembayaran akan diteruskan ke kreator dan
              pesanan dinyatakan selesai secara resmi.
            </p>
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowConfirmModal(false)}
                disabled={completeAction.isPending}
                className="inline-flex min-h-11 items-center justify-center rounded-xl border border-[var(--border)] px-4 text-sm font-medium transition hover:bg-[var(--border)] active:scale-[0.98]"
              >
                Batal
              </button>
              <button
                type="button"
                onClick={handleAcceptDelivery}
                disabled={completeAction.isPending}
                className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[var(--primary)] px-5 text-sm font-medium text-[var(--primary-foreground)] shadow-sm transition active:scale-[0.98] disabled:opacity-60"
              >
                {completeAction.isPending ? "Memproses…" : "Ya, terima hasil"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Dispute Modal */}
      <DisputeModal
        bookingId={booking.id}
        isOpen={showDisputeModal}
        onClose={() => setShowDisputeModal(false)}
        onSuccess={(newDispute) => {
          setDispute(newDispute);
          setShowDisputeModal(false);
          workspaceQuery.refetch();
        }}
      />

      <BottomNavigation />
    </main>
  );
}
