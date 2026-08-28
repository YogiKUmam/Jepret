"use client";

import Link from "next/link";

import type { BookingStatus, Workspace } from "@/lib/api";
import { BOOKING_STATUS_LABELS } from "@/lib/bookings";
import { formatIdr } from "@/lib/format";

function formatEventDate(dateStr: string) {
  try {
    return new Intl.DateTimeFormat("id-ID", {
      day: "numeric",
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(new Date(`${dateStr}T00:00:00Z`));
  } catch {
    return dateStr;
  }
}

const ORDERED_STATUSES: BookingStatus[] = [
  "confirmed",
  "in_progress",
  "delivered",
  "completed",
];

const STATUS_TITLES: Record<string, string> = {
  confirmed: "Terkonfirmasi",
  in_progress: "Sesi Berlangsung",
  delivered: "Hasil Dikirim",
  completed: "Selesai",
};

export interface WorkspaceHeaderProps {
  workspace: Workspace;
  onStart?: () => void;
  isStarting?: boolean;
  onDeliver?: () => void;
  isDelivering?: boolean;
  onAccept?: () => void;
  isAccepting?: boolean;
  actionError?: string | null;
}

export function WorkspaceHeader({
  workspace,
  onStart,
  isStarting = false,
  onDeliver,
  isDelivering = false,
  onAccept,
  isAccepting = false,
  actionError,
}: WorkspaceHeaderProps) {
  const { role, booking, deliverables } = workspace;
  const counterpartyName =
    role === "creator" ? booking.client_name : booking.creator.display_name;
  const roleLabel = role === "creator" ? "Kreator" : "Klien";
  const currentStatusIndex = ORDERED_STATUSES.indexOf(booking.status);
  const hasDeliverables = deliverables && deliverables.length > 0;

  const canStart = role === "creator" && booking.status === "confirmed";
  const canDeliver = role === "creator" && booking.status === "in_progress";
  const canAccept = role === "client" && booking.status === "delivered";

  return (
    <header className="rounded-3xl border border-[var(--border)] bg-[var(--background)] p-5 text-[var(--foreground)] shadow-sm sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-[var(--border)] px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
              {roleLabel}
            </span>
            <span className="text-xs text-[var(--muted)]">·</span>
            <span className="text-xs font-medium text-[var(--muted)]">
              {BOOKING_STATUS_LABELS[booking.status] ?? booking.status}
            </span>
          </div>
          <h1 className="mt-1 font-serif text-2xl font-bold sm:text-3xl">
            {counterpartyName}
          </h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {formatEventDate(booking.event_date)} · {booking.event_city} ·{" "}
            <span className="font-semibold text-[var(--foreground)]">
              {formatIdr(booking.quoted_price_idr)}
            </span>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {canStart && onStart ? (
            <button
              type="button"
              onClick={onStart}
              disabled={isStarting}
              className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[var(--primary)] px-5 text-sm font-medium text-[var(--primary-foreground)] shadow-sm transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isStarting ? "Memulai sesi…" : "Mulai sesi"}
            </button>
          ) : null}

          {canDeliver && onDeliver ? (
            <button
              type="button"
              onClick={onDeliver}
              disabled={isDelivering || !hasDeliverables}
              title={
                !hasDeliverables
                  ? "Tambahkan minimal satu berkas hasil sebelum mengirim."
                  : undefined
              }
              className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[var(--primary)] px-5 text-sm font-medium text-[var(--primary-foreground)] shadow-sm transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isDelivering ? "Mengirim hasil…" : "Kirim hasil"}
            </button>
          ) : null}

          {canAccept && onAccept ? (
            <button
              type="button"
              onClick={onAccept}
              disabled={isAccepting}
              className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[var(--primary)] px-5 text-sm font-medium text-[var(--primary-foreground)] shadow-sm transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isAccepting ? "Memproses…" : "Terima hasil"}
            </button>
          ) : null}

          <Link
            href={`/booking/${booking.id}/pembayaran`}
            className="inline-flex min-h-11 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 text-sm font-medium text-[var(--surface-foreground)] transition hover:bg-[var(--border)] active:scale-[0.98]"
          >
            Lihat pembayaran
          </Link>
        </div>
      </div>

      {actionError ? (
        <p
          role="alert"
          className="mt-4 rounded-xl bg-red-500/10 p-3 text-sm text-red-500"
        >
          {actionError}
        </p>
      ) : null}

      {/* Progress timeline */}
      <nav
        aria-label="Status Progres Booking"
        className="mt-6 border-t border-[var(--border)] pt-4"
      >
        <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {ORDERED_STATUSES.map((statusKey, index) => {
            const isCurrent = booking.status === statusKey;
            const isCompleted =
              currentStatusIndex !== -1 && currentStatusIndex > index;
            return (
              <li
                key={statusKey}
                className={`flex items-center gap-2 rounded-xl p-2 text-xs font-medium ${
                  isCurrent
                    ? "bg-[var(--surface)] text-[var(--primary)] font-semibold shadow-xs"
                    : isCompleted
                      ? "text-[var(--foreground)]"
                      : "text-[var(--muted)] opacity-60"
                }`}
              >
                <span
                  aria-hidden
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] ${
                    isCurrent
                      ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                      : isCompleted
                        ? "bg-emerald-600 text-white"
                        : "border border-[var(--border)]"
                  }`}
                >
                  {isCompleted ? "✓" : index + 1}
                </span>
                <span>{STATUS_TITLES[statusKey] ?? statusKey}</span>
              </li>
            );
          })}
        </ol>
      </nav>
    </header>
  );
}
