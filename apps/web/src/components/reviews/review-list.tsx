"use client";

import { useEffect, useState } from "react";

import type { Review, ReviewPage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { listCreatorReviews } from "@/lib/reviews";

interface ReviewListProps {
  creatorId: string;
  initialRatingAverage?: number;
  initialReviewCount?: number;
}

export function ReviewList({
  creatorId,
  initialRatingAverage = 0,
  initialReviewCount = 0,
}: ReviewListProps) {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [ratingAverage, setRatingAverage] =
    useState<number>(initialRatingAverage);
  const [reviewCount, setReviewCount] = useState<number>(initialReviewCount);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    listCreatorReviews(creatorId)
      .then((data: ReviewPage) => {
        if (!isMounted) return;
        setReviews(data.items);
        setRatingAverage(data.rating_average);
        setReviewCount(data.review_count);
        setNextCursor(data.next_cursor);
      })
      .catch((err: unknown) => {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : "Gagal memuat ulasan.");
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [creatorId]);

  const handleLoadMore = async () => {
    if (!nextCursor || isLoadingMore) return;
    setIsLoadingMore(true);
    try {
      const data = await listCreatorReviews(creatorId, nextCursor);
      setReviews((prev) => [...prev, ...data.items]);
      setNextCursor(data.next_cursor);
    } catch {
      // Keep existing list
    } finally {
      setIsLoadingMore(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-28 animate-pulse rounded-[24px] bg-white/[0.04]" />
        <div className="h-24 animate-pulse rounded-[20px] bg-white/[0.04]" />
        <div className="h-24 animate-pulse rounded-[20px] bg-white/[0.04]" />
      </div>
    );
  }

  if (error) {
    return (
      <div
        role="alert"
        className="rounded-2xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-400"
      >
        {error}
      </div>
    );
  }

  return (
    <section aria-label="Ulasan Klien" className="space-y-6">
      {/* Rating Summary Hero Card */}
      <div className="flex flex-col items-center justify-between gap-4 rounded-[28px] border border-white/[0.08] bg-[#1C1C1E]/80 p-6 shadow-sm backdrop-blur-2xl sm:flex-row sm:px-8">
        <div className="flex items-center gap-4">
          <div className="text-center sm:text-left">
            <span className="font-serif text-4xl font-bold text-[var(--foreground)] sm:text-5xl">
              {reviewCount > 0 ? ratingAverage.toFixed(1) : "0.0"}
            </span>
            <span className="text-lg text-[var(--muted)]"> / 5.0</span>
          </div>
          <div className="space-y-1">
            <div className="flex text-amber-400">
              {[1, 2, 3, 4, 5].map((star) => (
                <span
                  key={star}
                  className={
                    star <= Math.round(ratingAverage)
                      ? "text-amber-400"
                      : "text-white/20"
                  }
                >
                  ★
                </span>
              ))}
            </div>
            <p className="text-xs text-[var(--muted)]">
              Berdasarkan {reviewCount} ulasan klien terverifikasi
            </p>
          </div>
        </div>
      </div>

      {/* Review Items List */}
      {reviews.length === 0 ? (
        <div className="rounded-[24px] border border-dashed border-white/[0.1] p-8 text-center text-sm text-[var(--muted)]">
          Belum ada ulasan untuk kreator ini. Jadilah yang pertama memberikan
          ulasan setelah sesi foto Anda selesai!
        </div>
      ) : (
        <div className="space-y-4">
          {reviews.map((review) => (
            <article
              key={review.id}
              className="rounded-[24px] border border-white/[0.06] bg-white/[0.02] p-5 backdrop-blur-md"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h4 className="text-sm font-semibold text-[var(--foreground)]">
                    {review.client_full_name}
                  </h4>
                  <div className="mt-1 flex items-center gap-1.5 text-xs text-amber-400">
                    <span>{"★".repeat(review.rating)}</span>
                    <span className="text-white/20">
                      {"★".repeat(5 - review.rating)}
                    </span>
                  </div>
                </div>
                <time
                  dateTime={review.created_at}
                  className="text-xs text-[var(--muted)]"
                >
                  {formatDate(review.created_at.split("T")[0])}
                </time>
              </div>
              {review.comment && (
                <p className="mt-3 text-sm text-neutral-300 leading-relaxed">
                  {review.comment}
                </p>
              )}
            </article>
          ))}

          {nextCursor && (
            <div className="pt-2 text-center">
              <button
                type="button"
                disabled={isLoadingMore}
                onClick={handleLoadMore}
                className="rounded-xl border border-white/[0.1] bg-white/[0.04] px-5 py-2.5 text-xs font-semibold text-[var(--foreground)] transition-all hover:bg-white/[0.08] active:scale-95 disabled:opacity-50"
              >
                {isLoadingMore
                  ? "Memuat lebih banyak..."
                  : "Muat Ulasan Lainnya"}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
