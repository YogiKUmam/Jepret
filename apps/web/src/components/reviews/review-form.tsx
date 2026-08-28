"use client";

import { useState } from "react";

import type { Review } from "@/lib/api";
import { createReview } from "@/lib/reviews";

interface ReviewFormProps {
  bookingId: string;
  onSuccess: (review: Review) => void;
  onCancel?: () => void;
}

export function ReviewForm({
  bookingId,
  onSuccess,
  onCancel,
}: ReviewFormProps) {
  const [rating, setRating] = useState<number>(5);
  const [hoverRating, setHoverRating] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const activeRating = hoverRating ?? rating;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (rating < 1 || rating > 5) {
      setErrorMessage("Silakan pilih rating antara 1 sampai 5 bintang.");
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const review = await createReview(bookingId, rating, comment.trim());
      onSuccess(review);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Gagal mengirim ulasan. Silakan coba kembali.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-[28px] border border-white/[0.08] bg-[#1C1C1E]/80 p-6 shadow-[0_14px_36px_-6px_rgba(0,0,0,0.3)] backdrop-blur-2xl"
    >
      <h3 className="font-serif text-xl text-[var(--foreground)]">
        Beri Ulasan untuk Kreator
      </h3>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Bagikan pengalaman Anda menggunakan jasa kreator ini untuk membantu
        pengguna lain.
      </p>

      {errorMessage && (
        <div
          role="alert"
          className="mt-4 rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-400"
        >
          {errorMessage}
        </div>
      )}

      {/* Star Rating Picker */}
      <div className="mt-6">
        <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
          Rating Bintang
        </label>
        <div
          role="radiogroup"
          aria-label="Rating Bintang"
          className="mt-2 flex items-center gap-2"
        >
          {[1, 2, 3, 4, 5].map((star) => {
            const isFilled = star <= activeRating;
            return (
              <button
                key={star}
                type="button"
                role="radio"
                aria-checked={rating === star}
                aria-label={`Beri ${star} bintang`}
                disabled={isSubmitting}
                onClick={() => setRating(star)}
                onMouseEnter={() => setHoverRating(star)}
                onMouseLeave={() => setHoverRating(null)}
                className="grid h-10 w-10 place-items-center rounded-xl bg-white/[0.04] text-2xl transition-all duration-150 hover:bg-white/[0.1] active:scale-95 disabled:opacity-50"
              >
                <span className={isFilled ? "text-amber-400" : "text-white/20"}>
                  ★
                </span>
              </button>
            );
          })}
          <span className="ml-2 text-sm font-medium text-amber-400">
            {activeRating === 5 && "Sangat Memuaskan"}
            {activeRating === 4 && "Memuaskan"}
            {activeRating === 3 && "Cukup Baik"}
            {activeRating === 2 && "Kurang Memuaskan"}
            {activeRating === 1 && "Tidak Memuaskan"}
          </span>
        </div>
      </div>

      {/* Comment Field */}
      <div className="mt-5">
        <div className="flex items-center justify-between">
          <label
            htmlFor="review-comment"
            className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted)]"
          >
            Komentar (Opsional)
          </label>
          <span className="text-xs text-[var(--muted)]">
            {comment.length} / 1000
          </span>
        </div>
        <textarea
          id="review-comment"
          rows={3}
          maxLength={1000}
          disabled={isSubmitting}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Tulis ulasan Anda tentang kualitas hasil foto, ketepatan waktu, dan keramahan..."
          className="mt-2 w-full rounded-2xl border border-white/[0.08] bg-black/20 p-4 text-sm text-[var(--foreground)] placeholder:text-white/30 focus:border-[var(--primary)] focus:outline-none focus:ring-1 focus:ring-[var(--primary)] disabled:opacity-50"
        />
      </div>

      {/* Actions */}
      <div className="mt-6 flex items-center justify-end gap-3">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            disabled={isSubmitting}
            className="rounded-xl px-4 py-2.5 text-sm font-medium text-[var(--muted)] transition-colors hover:text-white active:scale-95 disabled:opacity-50"
          >
            Batal
          </button>
        )}
        <button
          type="submit"
          disabled={isSubmitting}
          className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[var(--primary)] px-6 py-2.5 text-sm font-semibold text-black shadow-sm transition-all duration-200 hover:brightness-110 active:scale-[0.96] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? "Mengirim Ulasan..." : "Kirim Ulasan"}
        </button>
      </div>
    </form>
  );
}
