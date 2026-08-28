"use client";

import { useEffect, useState } from "react";

import {
  approveCreatorApplication,
  listCreatorApplications,
  rejectCreatorApplication,
} from "@/lib/admin";
import type { CreatorApplication } from "@/lib/api";
import { formatDate, formatIdr } from "@/lib/format";

export default function AdminCreatorApplicationsPage() {
  const [applications, setApplications] = useState<CreatorApplication[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  useEffect(() => {
    let isMounted = true;
    listCreatorApplications()
      .then((data) => {
        if (isMounted) setApplications(data);
      })
      .catch((err: unknown) => {
        if (isMounted) {
          setFeedback({
            type: "error",
            message:
              err instanceof Error
                ? err.message
                : "Gagal memuat aplikasi kreator.",
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

  const handleApprove = async (profileId: string) => {
    setProcessingId(profileId);
    setFeedback(null);
    try {
      await approveCreatorApplication(profileId);
      setApplications((prev) =>
        prev.filter((app) => app.profile.id !== profileId),
      );
      setFeedback({
        type: "success",
        message: "Profil kreator berhasil disetujui.",
      });
    } catch (err: unknown) {
      setFeedback({
        type: "error",
        message:
          err instanceof Error ? err.message : "Gagal menyetujui aplikasi.",
      });
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (profileId: string) => {
    setProcessingId(profileId);
    setFeedback(null);
    try {
      await rejectCreatorApplication(profileId);
      setApplications((prev) =>
        prev.filter((app) => app.profile.id !== profileId),
      );
      setFeedback({
        type: "success",
        message: "Profil kreator berhasil ditolak.",
      });
    } catch (err: unknown) {
      setFeedback({
        type: "error",
        message: err instanceof Error ? err.message : "Gagal menolak aplikasi.",
      });
    } finally {
      setProcessingId(null);
    }
  };

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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-serif text-3xl font-bold text-[var(--foreground)]">
            Verifikasi Profil Kreator
          </h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Tinjau portofolio, data kota, dan tarif pembuat konten sebelum
            ditampilkan ke publik.
          </p>
        </div>
        <span className="rounded-full bg-white/[0.05] px-3 py-1 text-xs font-semibold text-white">
          {applications.length} Menunggu
        </span>
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

      {applications.length === 0 ? (
        <div className="rounded-[32px] border border-dashed border-white/[0.1] p-12 text-center">
          <p className="text-sm text-[var(--muted)]">
            Tidak ada pengajuan kreator yang sedang menunggu verifikasi saat
            ini.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {applications.map(({ profile, user_email, user_full_name }) => (
            <article
              key={profile.id}
              className="rounded-[28px] border border-white/[0.08] bg-[#1C1C1E]/80 p-6 backdrop-blur-2xl"
            >
              <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="font-serif text-xl font-bold text-white">
                      {profile.display_name}
                    </h2>
                    <span className="rounded-full bg-amber-500/10 px-2.5 py-0.5 text-xs font-medium text-amber-400">
                      Pending
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-[var(--muted)]">
                    Pemilik akun:{" "}
                    <span className="text-white">{user_full_name}</span> (
                    {user_email})
                  </p>
                  <p className="mt-0.5 text-xs text-[var(--muted)]">
                    Kota: <span className="text-white">{profile.city}</span> ·
                    Spesialisasi:{" "}
                    <span className="text-white">{profile.specialty}</span> ·
                    Tarif mulai:{" "}
                    <span className="font-semibold text-white">
                      {formatIdr(profile.starting_price_idr)}
                    </span>
                  </p>
                  {profile.submitted_at && (
                    <p className="mt-1 text-xs text-[var(--muted)]">
                      Diajukan pada:{" "}
                      {formatDate(profile.submitted_at.split("T")[0])}
                    </p>
                  )}
                </div>

                {/* Action Buttons */}
                <div className="flex items-center gap-2 sm:self-start">
                  <button
                    type="button"
                    disabled={processingId === profile.id}
                    onClick={() => handleReject(profile.id)}
                    className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-2 text-xs font-semibold text-red-300 transition-all hover:bg-red-500/20 active:scale-95 disabled:opacity-50"
                  >
                    {processingId === profile.id ? "Memproses..." : "Tolak"}
                  </button>
                  <button
                    type="button"
                    disabled={processingId === profile.id}
                    onClick={() => handleApprove(profile.id)}
                    className="rounded-xl bg-[var(--primary)] px-4 py-2 text-xs font-semibold text-black transition-all hover:brightness-110 active:scale-95 disabled:opacity-50"
                  >
                    {processingId === profile.id
                      ? "Memproses..."
                      : "Setujui Profil"}
                  </button>
                </div>
              </div>

              {profile.bio && (
                <div className="mt-4 rounded-2xl border border-white/[0.04] bg-black/20 p-3.5 text-xs text-neutral-300">
                  <p className="font-semibold text-white/80">
                    Bio / Deskripsi Kreator:
                  </p>
                  <p className="mt-1 whitespace-pre-wrap">{profile.bio}</p>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
