import { apiFetch, Review, ReviewPage } from "./api";

export async function createReview(
  bookingId: string,
  rating: number,
  comment?: string,
): Promise<Review> {
  return apiFetch<Review>(`/bookings/${bookingId}/reviews`, {
    method: "POST",
    body: JSON.stringify({ rating, comment: comment || null }),
  });
}

export async function getBookingReview(
  bookingId: string,
): Promise<Review | null> {
  return apiFetch<Review | null>(`/bookings/${bookingId}/review`);
}

export async function listCreatorReviews(
  creatorId: string,
  cursor?: string | null,
  limit: number = 10,
): Promise<ReviewPage> {
  const params = new URLSearchParams();
  if (cursor) params.set("cursor", cursor);
  params.set("limit", String(limit));
  const queryString = params.toString();
  return apiFetch<ReviewPage>(
    `/creators/${creatorId}/reviews${queryString ? `?${queryString}` : ""}`,
  );
}
