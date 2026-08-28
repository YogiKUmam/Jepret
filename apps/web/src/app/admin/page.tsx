"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getAdminOverview } from "@/lib/admin";
import type { AdminOverview } from "@/lib/api";
import { formatIdr } from "@/lib/format";

export default function AdminOverviewPage() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    getAdminOverview()
      .then((data) => {
        if (isMounted) setOverview(data);
      })
      .catch((err: unknown) => {
        if (isMounted) {
          setError(
            err instanceof Error
              ? err.message
              : "Gagal memuat data ringkasan admin.",
          );
        }
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-10 w-48 animate-pulse rounded-xl bg-white/[0.04]" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div
              key={i}
              className="h-36 animate-pulse rounded-[28px] bg-white/[0.04]"
            />
          ))}
        </div>
      </div>
    );
  }

  if (error || !overview) {
    return (
      <div
        role="alert"
        className="rounded-2xl border border-red-500/20 bg-red-500/10 p-6 text-red-400"
      >
        <h2 className="font-serif text-lg font-bold">Gagal Memuat Ringkasan</h2>
        <p className="mt-1 text-sm">{error || "Data tidak tersedia."}</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-serif text-3xl font-bold text-[var(--foreground)] sm:text-4xl">
          Ringkasan Operasional
        </h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Pantau metrik kesehatan platform, aplikasi kreator, dan sengketa
          transaksi secara real-time.
        </p>
      </div>

      {/* Bento Grid Metrics */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {/* GMV Hero Card */}
        <div className="sm:col-span-2 rounded-[28px] border border-white/[0.08] bg-[#1C1C1E]/80 p-6 shadow-sm backdrop-blur-2xl sm:p-8">
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--primary)]">
            Total Gross Merchandise Value (GMV)
          </p>
          <h2 className="mt-3 font-serif text-3xl font-bold text-white sm:text-5xl">
            {formatIdr(overview.total_gmv_idr)}
          </h2>
          <p className="mt-2 text-xs text-[var(--muted)]">
            Total perputaran dana dari pembayaran terverifikasi, escrow
            tertahan, dan pelepasan sukses.
          </p>
        </div>

        {/* Pending Applications Card */}
        <Link
          href="/admin/kreator"
          className="group rounded-[28px] border border-amber-500/20 bg-amber-500/10 p-6 transition-all duration-200 hover:border-amber-500/40 active:scale-[0.98]"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-amber-400">
              Verifikasi Kreator
            </span>
            <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs text-amber-300">
              Perlu Tindakan
            </span>
          </div>
          <h3 className="mt-4 font-serif text-4xl font-bold text-white">
            {overview.pending_creator_applications}
          </h3>
          <p className="mt-2 text-xs text-amber-200/80 group-hover:text-amber-200">
            Aplikasi profil kreator menunggu peninjauan →
          </p>
        </Link>

        {/* Active Disputes Card */}
        <Link
          href="/admin/sengketa"
          className="group rounded-[28px] border border-red-500/20 bg-red-500/10 p-6 transition-all duration-200 hover:border-red-500/40 active:scale-[0.98]"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-red-400">
              Sengketa Aktif
            </span>
            <span className="rounded-full bg-red-500/20 px-2 py-0.5 text-xs text-red-300">
              Mediasi
            </span>
          </div>
          <h3 className="mt-4 font-serif text-4xl font-bold text-white">
            {overview.active_disputes}
          </h3>
          <p className="mt-2 text-xs text-red-200/80 group-hover:text-red-200">
            Sengketa booking memerlukan keputusan admin →
          </p>
        </Link>

        {/* Total Bookings */}
        <div className="rounded-[28px] border border-white/[0.08] bg-[#1C1C1E]/80 p-6 backdrop-blur-2xl">
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
            Total Booking Sesi
          </p>
          <h3 className="mt-4 font-serif text-3xl font-bold text-white">
            {overview.total_bookings}
          </h3>
          <p className="mt-2 text-xs text-[var(--muted)]">
            Semua permintaan dan transaksi booking yang terdaftar.
          </p>
        </div>

        {/* Total Users & Creators */}
        <div className="rounded-[28px] border border-white/[0.08] bg-[#1C1C1E]/80 p-6 backdrop-blur-2xl">
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
            Basis Pengguna & Kreator
          </p>
          <div className="mt-4 flex items-baseline gap-6">
            <div>
              <span className="font-serif text-3xl font-bold text-white">
                {overview.total_users}
              </span>
              <p className="text-xs text-[var(--muted)]">Klien</p>
            </div>
            <div>
              <span className="font-serif text-3xl font-bold text-white">
                {overview.total_creators}
              </span>
              <p className="text-xs text-[var(--muted)]">Kreator</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
