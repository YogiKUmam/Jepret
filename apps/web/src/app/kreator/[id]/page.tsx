"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { AppHeader } from "@/components/layout/app-header";
import { BottomNavigation } from "@/components/layout/bottom-navigation";
import { ReviewList } from "@/components/reviews/review-list";
import { useCreator } from "@/lib/creators";
import { formatIdr } from "@/lib/format";

export default function KreatorDetailPage() {
  const params = useParams<{ id: string }>();
  const { data: creator, isPending, isError } = useCreator(params.id);

  return (
    <main className="min-h-screen bg-[var(--surface)] pb-24 text-[var(--surface-foreground)]">
      <AppHeader />
      <section className="mx-auto max-w-3xl px-5 py-10">
        {isPending ? (
          <div aria-hidden className="space-y-4">
            <div className="h-56 animate-pulse rounded-2xl bg-[var(--border)]" />
            <div className="h-8 w-2/3 animate-pulse rounded bg-[var(--border)]" />
            <div className="h-4 w-1/2 animate-pulse rounded bg-[var(--border)]" />
          </div>
        ) : isError ? (
          <p role="alert" className="text-[var(--muted)]">
            Halaman belum dapat dimuat. Silakan coba kembali.
          </p>
        ) : creator === null ? (
          <div>
            <h1 className="font-serif text-3xl">Kreator tidak ditemukan.</h1>
            <p className="mt-3 text-[var(--muted)]">
              Profil ini mungkin sudah tidak tersedia.
            </p>
            <Link
              href="/"
              className="mt-6 inline-block font-medium text-[var(--primary)]"
            >
              Kembali ke beranda
            </Link>
          </div>
        ) : creator ? (
          <article className="space-y-8">
            <div>
              <div
                aria-hidden
                className="grid h-56 place-items-center rounded-2xl bg-[linear-gradient(135deg,#5b5148,#1f1d1b)]"
              >
                <span className="font-serif text-6xl text-[#cfc5b8]">
                  {creator.display_name.charAt(0)}
                </span>
              </div>
              <div className="mt-6 flex items-center justify-between">
                <p className="text-xs font-semibold text-[var(--primary)]">
                  TERVERIFIKASI
                </p>
                {creator.review_count > 0 && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-400">
                    <span aria-hidden>★</span>
                    <span>{creator.rating_average.toFixed(1)}</span>
                    <span className="text-[var(--muted)]">
                      ({creator.review_count} ulasan)
                    </span>
                  </span>
                )}
              </div>
              <h1 className="mt-2 font-serif text-4xl">
                {creator.display_name}
              </h1>
              <p className="mt-2 text-[var(--muted)]">
                {creator.city} · {creator.specialty}
              </p>
              {creator.bio ? (
                <p className="mt-5 text-neutral-300">{creator.bio}</p>
              ) : null}
              <p className="mt-6 text-lg font-semibold">
                Mulai {formatIdr(creator.starting_price_idr)}
              </p>
              <Link
                href={`/kreator/${creator.id}/booking`}
                className="mt-6 inline-block min-h-11 rounded-xl bg-[var(--primary)] px-6 py-3 font-semibold text-black transition-transform active:scale-95"
              >
                Ajukan booking
              </Link>
            </div>

            <hr className="border-white/[0.08]" />

            <div>
              <h2 className="mb-4 font-serif text-2xl text-[var(--foreground)]">
                Ulasan Klien
              </h2>
              <ReviewList
                creatorId={creator.id}
                initialRatingAverage={creator.rating_average}
                initialReviewCount={creator.review_count}
              />
            </div>
          </article>
        ) : null}
      </section>
      <BottomNavigation />
    </main>
  );
}
