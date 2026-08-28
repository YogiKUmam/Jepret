"use client";

import { useEffect, useState } from "react";

import { listAdminDisputes, resolveAdminDispute } from "@/lib/admin";
import type { Dispute } from "@/lib/api";
import { formatDate } from "@/lib/format";

const REASON_LABELS: Record<string, string> = {
  not_delivered: "Hasil Tidak Diserahkan",
  quality_issue: "Kualitas Tidak Sesuai",
  unresponsive: "Kreator Tidak Merespons",
  other: "Lainnya",
};

export default function AdminDisputesPage() {
  const [disputes, setDisputes] = useState<Dispute[]>([]);
  const [filter, setFilter] = useState<"all" | "pending" | "resolved">(
    "pending",
  );
  const [isLoading, setIsLoading] = useState(true);
  const [activeDisputeId, setActiveDisputeId] = useState<string | null>(null);
  const [resolutionChoice, setResolutionChoice] = useState<
    "resolved_client" | "resolved_creator"
  >("resolved_client");
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  useEffect(() => {
    let isMounted = true;
    listAdminDisputes()
      .then((data) => {
        if (isMounted) setDisputes(data);
      })
      .catch((err: unknown) => {
        if (isMounted) {
          setFeedback({
            type: "error",
            message:
              err instanceof Error
                ? err.message
                : "Gagal memuat daftar sengketa.",
          });
        }
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const handleResolve = async (disputeId: string) => {
    if (resolutionNotes.trim().length < 5) {
      setFeedback({
        type: "error",
        message: "Catatan resolusi minimal 5 karakter.",
      });
      return;
    }

    setIsSubmitting(true);
    setFeedback(null);

    try {
      const updated = await resolveAdminDispute(
        disputeId,
        resolutionChoice,
        resolutionNotes.trim(),
      );
      setDisputes((prev) =>
        prev.map((d) => (d.id === disputeId ? updated : d)),
      );
      setActiveDisputeId(null);
      setResolutionNotes("");
      setFeedback({
        type: "success",
        message: `Sengketa berhasil diselesaikan (${resolutionChoice === "resolved_client" ? "Refund Klien" : "Release Kreator"}).`,
      });
    } catch (err: unknown) {
      setFeedback({
        type: "error",
        message:
          err instanceof Error ? err.message : "Gagal menyelesaikan sengketa.",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredDisputes = disputes.filter((d) => {
    const isPending = d.status === "open" || d.status === "under_review";
    if (filter === "pending") return isPending;
    if (filter === "resolved") return !isPending;
    return true;
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-10 w-64 animate-pulse rounded-xl bg-white/[0.04]" />
        <div className="h-44 animate-pulse rounded-[28px] bg-white/[0.04]" />
        <div className="h-44 animate-pulse rounded-[28px] bg-white/[0.04]" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="font-serif text-3xl font-bold text-[var(--foreground)]">
            Manajemen Sengketa & Mediasi
          </h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Tinjau bukti dan buat keputusan mediasi resmi untuk pelepasan atau
            pengembalian dana escrow.
          </p>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1 rounded-xl bg-white/[0.04] p-1 border border-white/[0.08]">
          <button
            type="button"
            onClick={() => setFilter("pending")}
            className={`rounded-lg px-3 py-1 text-xs font-semibold transition-all ${
              filter === "pending"
                ? "bg-[var(--primary)] text-black"
                : "text-[var(--muted)] hover:text-white"
            }`}
          >
            Aktif / Perlu Mediasi
          </button>
          <button
            type="button"
            onClick={() => setFilter("resolved")}
            className={`rounded-lg px-3 py-1 text-xs font-semibold transition-all ${
              filter === "resolved"
                ? "bg-[var(--primary)] text-black"
                : "text-[var(--muted)] hover:text-white"
            }`}
          >
            Selesai
          </button>
          <button
            type="button"
            onClick={() => setFilter("all")}
            className={`rounded-lg px-3 py-1 text-xs font-semibold transition-all ${
              filter === "all"
                ? "bg-[var(--primary)] text-black"
                : "text-[var(--muted)] hover:text-white"
            }`}
          >
            Semua ({disputes.length})
          </button>
        </div>
      </div>

      {feedback && (
        <div
          role="alert"
          className={`rounded-2xl border p-4 text-sm ${
            feedback.type === "success"
              ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
              : "border-red-500/20 bg-red-500/10 text-red-400"
          }`}
        >
          {feedback.message}
        </div>
      )}

      {filteredDisputes.length === 0 ? (
        <div className="rounded-[32px] border border-dashed border-white/[0.1] p-12 text-center">
          <p className="text-sm text-[var(--muted)]">
            Tidak ada sengketa yang sesuai dengan filter ini.
          </p>
        </div>
      ) : (
        <div className="space-y-5">
          {filteredDisputes.map((dispute) => {
            const isPending =
              dispute.status === "open" || dispute.status === "under_review";
            const isResolvingThis = activeDisputeId === dispute.id;

            return (
              <article
                key={dispute.id}
                className="rounded-[28px] border border-white/[0.08] bg-[#1C1C1E]/80 p-6 backdrop-blur-2xl"
              >
                <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-lg">⚖️</span>
                      <h2 className="font-serif text-lg font-bold text-white">
                        {REASON_LABELS[dispute.reason_category] ||
                          dispute.reason_category}
                      </h2>
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                          isPending
                            ? "bg-amber-500/20 text-amber-300"
                            : dispute.status === "resolved_client"
                              ? "bg-sky-500/20 text-sky-300"
                              : "bg-emerald-500/20 text-emerald-300"
                        }`}
                      >
                        {dispute.status}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-[var(--muted)]">
                      Booking ID:{" "}
                      <span className="font-mono text-white/80">
                        {dispute.booking_id}
                      </span>
                    </p>
                    <p className="mt-0.5 text-xs text-[var(--muted)]">
                      Diajukan oleh:{" "}
                      <span className="text-white">
                        {dispute.opened_by_full_name}
                      </span>{" "}
                      · {formatDate(dispute.created_at.split("T")[0])}
                    </p>
                  </div>

                  {isPending && !isResolvingThis && (
                    <button
                      type="button"
                      onClick={() => {
                        setActiveDisputeId(dispute.id);
                        setResolutionNotes("");
                      }}
                      className="rounded-xl bg-amber-500/20 px-4 py-2 text-xs font-semibold text-amber-300 hover:bg-amber-500/30 active:scale-95"
                    >
                      Buka Mediasi / Putusan
                    </button>
                  )}
                </div>

                <div className="mt-4 rounded-2xl border border-white/[0.04] bg-black/20 p-4 text-xs text-neutral-300">
                  <p className="font-semibold text-white/80">
                    Keterangan Masalah dari Klien:
                  </p>
                  <p className="mt-1 whitespace-pre-wrap leading-relaxed">
                    {dispute.description}
                  </p>
                </div>

                {/* Resolution display if resolved */}
                {dispute.resolution_notes && (
                  <div className="mt-4 rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-4 text-xs text-emerald-200">
                    <p className="font-semibold">
                      Catatan Keputusan Mediasi Admin:
                    </p>
                    <p className="mt-1">{dispute.resolution_notes}</p>
                    {dispute.resolved_at && (
                      <p className="mt-2 text-[10px] text-emerald-300/70">
                        Diselesaikan pada:{" "}
                        {formatDate(dispute.resolved_at.split("T")[0])}
                      </p>
                    )}
                  </div>
                )}

                {/* Active Resolution Decision Form */}
                {isResolvingThis && (
                  <div className="mt-5 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-5">
                    <h3 className="text-sm font-semibold text-amber-300">
                      Formulir Keputusan Mediasi Sengketa
                    </h3>

                    <div className="mt-4 space-y-3">
                      <div>
                        <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
                          Pilihan Keputusan
                        </label>
                        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <label
                            className={`flex cursor-pointer items-center gap-2.5 rounded-xl border p-3 text-xs transition ${
                              resolutionChoice === "resolved_client"
                                ? "border-sky-400 bg-sky-500/10 text-sky-200"
                                : "border-white/10 text-white/70 hover:bg-white/[0.02]"
                            }`}
                          >
                            <input
                              type="radio"
                              name="res_choice"
                              value="resolved_client"
                              checked={resolutionChoice === "resolved_client"}
                              onChange={() =>
                                setResolutionChoice("resolved_client")
                              }
                              className="accent-sky-400"
                            />
                            <div>
                              <p className="font-semibold">
                                Menangkan Klien (Refund)
                              </p>
                              <p className="text-[10px] text-white/50">
                                Dana dikembalikan ke klien, booking dibatalkan
                              </p>
                            </div>
                          </label>

                          <label
                            className={`flex cursor-pointer items-center gap-2.5 rounded-xl border p-3 text-xs transition ${
                              resolutionChoice === "resolved_creator"
                                ? "border-emerald-400 bg-emerald-500/10 text-emerald-200"
                                : "border-white/10 text-white/70 hover:bg-white/[0.02]"
                            }`}
                          >
                            <input
                              type="radio"
                              name="res_choice"
                              value="resolved_creator"
                              checked={resolutionChoice === "resolved_creator"}
                              onChange={() =>
                                setResolutionChoice("resolved_creator")
                              }
                              className="accent-emerald-400"
                            />
                            <div>
                              <p className="font-semibold">
                                Menangkan Kreator (Release)
                              </p>
                              <p className="text-[10px] text-white/50">
                                Dana dilepas ke kreator, booking selesai
                              </p>
                            </div>
                          </label>
                        </div>
                      </div>

                      <div>
                        <label
                          htmlFor="res-notes"
                          className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted)]"
                        >
                          Catatan & Dasar Keputusan (Wajib)
                        </label>
                        <textarea
                          id="res-notes"
                          rows={3}
                          value={resolutionNotes}
                          onChange={(e) => setResolutionNotes(e.target.value)}
                          placeholder="Jelaskan alasan dan bukti yang mendasari keputusan mediasi ini..."
                          className="mt-2 w-full rounded-xl border border-white/10 bg-black/30 p-3 text-xs text-white placeholder:text-white/30 focus:border-[var(--primary)] focus:outline-none"
                        />
                      </div>

                      <div className="flex items-center justify-end gap-2 pt-2">
                        <button
                          type="button"
                          disabled={isSubmitting}
                          onClick={() => setActiveDisputeId(null)}
                          className="rounded-xl px-4 py-2 text-xs font-semibold text-[var(--muted)] hover:text-white"
                        >
                          Batal
                        </button>
                        <button
                          type="button"
                          disabled={
                            isSubmitting || resolutionNotes.trim().length < 5
                          }
                          onClick={() => handleResolve(dispute.id)}
                          className="rounded-xl bg-[var(--primary)] px-5 py-2 text-xs font-semibold text-black transition-all hover:brightness-110 active:scale-95 disabled:opacity-50"
                        >
                          {isSubmitting
                            ? "Menyimpan Putusan..."
                            : "Konfirmasi Keputusan"}
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
