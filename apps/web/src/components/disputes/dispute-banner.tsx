"use client";

import type { Dispute } from "@/lib/api";
import { formatDate } from "@/lib/format";

interface DisputeBannerProps {
  dispute: Dispute;
}

const REASON_LABELS: Record<string, string> = {
  not_delivered: "Hasil Tidak Diserahkan",
  quality_issue: "Kualitas Tidak Sesuai",
  unresponsive: "Kreator Tidak Merespons",
  other: "Lainnya",
};

export function DisputeBanner({ dispute }: DisputeBannerProps) {
  const isResolved =
    dispute.status === "resolved_client" ||
    dispute.status === "resolved_creator";

  return (
    <div
      role="region"
      aria-label="Informasi Sengketa"
      className={`rounded-[24px] border p-5 backdrop-blur-xl ${
        isResolved
          ? "border-emerald-500/20 bg-emerald-500/10"
          : "border-amber-500/30 bg-amber-500/10"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-lg">⚖️</span>
          <h3 className="text-sm font-semibold text-[var(--foreground)]">
            Status Sengketa:{" "}
            {REASON_LABELS[dispute.reason_category] || dispute.reason_category}
          </h3>
        </div>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider ${
            dispute.status === "open"
              ? "bg-amber-500/20 text-amber-300"
              : dispute.status === "resolved_client"
                ? "bg-sky-500/20 text-sky-300"
                : dispute.status === "resolved_creator"
                  ? "bg-emerald-500/20 text-emerald-300"
                  : "bg-white/10 text-white/70"
          }`}
        >
          {dispute.status === "open" && "Menunggu Mediasi Admin"}
          {dispute.status === "under_review" && "Sedang Ditinjau Admin"}
          {dispute.status === "resolved_client" && "Selesai: Refund ke Klien"}
          {dispute.status === "resolved_creator" &&
            "Selesai: Dimenangkan Kreator"}
          {dispute.status === "closed" && "Ditutup"}
        </span>
      </div>

      <p className="mt-3 text-xs text-neutral-300">
        <span className="font-semibold text-white/80">Diajukan oleh:</span>{" "}
        {dispute.opened_by_full_name} (
        {formatDate(dispute.created_at.split("T")[0])})
      </p>

      <p className="mt-1 text-xs text-neutral-300">
        <span className="font-semibold text-white/80">Keterangan:</span>{" "}
        {dispute.description}
      </p>

      {dispute.resolution_notes && (
        <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3 text-xs">
          <p className="font-semibold text-white/90">Catatan Mediasi Admin:</p>
          <p className="mt-1 text-neutral-300">{dispute.resolution_notes}</p>
        </div>
      )}
    </div>
  );
}
