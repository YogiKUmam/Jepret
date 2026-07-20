import Link from "next/link";

import type { CreatorProfile } from "@/lib/api";

const STATUS_LABELS: Record<CreatorProfile["status"], string> = {
  draft: "Draft — belum diajukan",
  pending: "Menunggu verifikasi",
  approved: "Terverifikasi",
  rejected: "Ditolak — silakan perbaiki dan ajukan ulang",
};

export function CreatorStatusCard({
  profile,
}: {
  profile: CreatorProfile | null;
}) {
  return (
    <section
      aria-labelledby="creator-status-heading"
      className="mt-8 rounded-2xl border border-[var(--border)] bg-white p-5"
    >
      <h2 id="creator-status-heading" className="font-serif text-xl">
        Profil kreator
      </h2>
      {profile ? (
        <>
          <p className="mt-2 text-sm">
            <span className="font-semibold">{profile.display_name}</span> ·{" "}
            {profile.city} · {profile.specialty}
          </p>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Status:{" "}
            <span className="font-medium">{STATUS_LABELS[profile.status]}</span>
          </p>
        </>
      ) : (
        <p className="mt-2 text-sm text-[var(--muted)]">
          Kamu belum punya profil kreator. Mulai terima pekerjaan dengan
          membuatnya.
        </p>
      )}
      <Link
        href="/profil/kreator"
        className="mt-4 inline-flex min-h-11 items-center rounded-xl border border-[var(--primary)] px-5 font-medium text-[var(--primary)]"
      >
        {profile ? "Kelola profil kreator" : "Jadi kreator"}
      </Link>
    </section>
  );
}
