"use client";

import { useState } from "react";

import type { Dispute, DisputeReason } from "@/lib/api";
import { openDispute } from "@/lib/disputes";

interface DisputeModalProps {
  bookingId: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (dispute: Dispute) => void;
}

const REASON_OPTIONS: { id: DisputeReason; label: string; desc: string }[] = [
  {
    id: "not_delivered",
    label: "Kreator Tidak Hadir / Hasil Belum Diserahkan",
    desc: "Kreator tidak datang ke lokasi acara atau tidak mengirimkan file hasil sesuai tenggat.",
  },
  {
    id: "quality_issue",
    label: "Kualitas Tidak Sesuai Kesepakatan",
    desc: "Hasil foto/video rusak, buram, atau tidak sesuai spesifikasi yang disepakati.",
  },
  {
    id: "unresponsive",
    label: "Kreator Tidak Dapat Dihubungi",
    desc: "Kreator berhenti merespons komunikasi selama proses pengerjaan.",
  },
  {
    id: "other",
    label: "Alasan Lainnya",
    desc: "Kendala operasional atau pelanggaran ketentuan lainnya.",
  },
];

export function DisputeModal({
  bookingId,
  isOpen,
  onClose,
  onSuccess,
}: DisputeModalProps) {
  const [reasonCategory, setReasonCategory] =
    useState<DisputeReason>("not_delivered");
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (description.trim().length < 10) {
      setError("Deskripsi sengketa minimal 10 karakter.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const dispute = await openDispute(
        bookingId,
        reasonCategory,
        description.trim(),
      );
      onSuccess(dispute);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Gagal mengajukan sengketa.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="dispute-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-md"
    >
      <div className="w-full max-w-lg rounded-[32px] border border-white/[0.1] bg-[#1C1C1E] p-6 shadow-2xl sm:p-8">
        <div className="flex items-start justify-between">
          <div>
            <h2
              id="dispute-dialog-title"
              className="font-serif text-2xl text-[var(--foreground)]"
            >
              Ajukan Sengketa / Komplain
            </h2>
            <p className="mt-1 text-xs text-[var(--muted)]">
              Tim admin Jepret akan meninjau riwayat chat, deliverables, dan
              memediasi penyelesaian.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="rounded-full p-2 text-[var(--muted)] hover:bg-white/[0.05] hover:text-white"
          >
            ✕
          </button>
        </div>

        {error && (
          <div
            role="alert"
            className="mt-4 rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-400"
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-5">
          {/* Reason Selection */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
              Pilih Alasan Sengketa
            </label>
            <div className="mt-2 space-y-2">
              {REASON_OPTIONS.map((opt) => {
                const isSelected = reasonCategory === opt.id;
                return (
                  <label
                    key={opt.id}
                    className={`flex cursor-pointer items-start gap-3 rounded-2xl border p-3.5 transition-all ${
                      isSelected
                        ? "border-[var(--primary)] bg-[var(--primary)]/10"
                        : "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04]"
                    }`}
                  >
                    <input
                      type="radio"
                      name="dispute_reason"
                      value={opt.id}
                      checked={isSelected}
                      onChange={() => setReasonCategory(opt.id)}
                      className="mt-0.5 accent-[var(--primary)]"
                    />
                    <div>
                      <p className="text-sm font-semibold text-[var(--foreground)]">
                        {opt.label}
                      </p>
                      <p className="text-xs text-[var(--muted)] mt-0.5">
                        {opt.desc}
                      </p>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Description */}
          <div>
            <div className="flex items-center justify-between">
              <label
                htmlFor="dispute-desc"
                className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted)]"
              >
                Detail Masalah (Wajib)
              </label>
              <span className="text-xs text-[var(--muted)]">
                {description.length} / 2000
              </span>
            </div>
            <textarea
              id="dispute-desc"
              rows={3}
              maxLength={2000}
              required
              disabled={isSubmitting}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Jelaskan secara rinci kronologi masalah dan kesepakatan yang tidak terpenuhi..."
              className="mt-2 w-full rounded-2xl border border-white/[0.08] bg-black/20 p-3.5 text-sm text-[var(--foreground)] placeholder:text-white/30 focus:border-[var(--primary)] focus:outline-none focus:ring-1 focus:ring-[var(--primary)] disabled:opacity-50"
            />
          </div>

          {/* Escrow Notice */}
          <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 p-3.5 text-xs text-amber-300">
            <span className="font-semibold">Perhatian:</span> Mengajukan
            sengketa akan menahan status booking dan pembayaran di escrow. Admin
            akan menghubungi kedua belah pihak jika diperlukan bukti tambahan.
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="rounded-xl px-4 py-2.5 text-sm font-medium text-[var(--muted)] hover:text-white disabled:opacity-50"
            >
              Batal
            </button>
            <button
              type="submit"
              disabled={isSubmitting || description.trim().length < 10}
              className="rounded-xl bg-red-600 px-5 py-2.5 text-sm font-semibold text-white transition-all hover:bg-red-500 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSubmitting ? "Mengirim..." : "Konfirmasi Sengketa"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
