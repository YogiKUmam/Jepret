import { apiFetch, Dispute, DisputeReason } from "./api";

export async function openDispute(
  bookingId: string,
  reasonCategory: DisputeReason,
  description: string,
): Promise<Dispute> {
  return apiFetch<Dispute>(`/bookings/${bookingId}/disputes`, {
    method: "POST",
    body: JSON.stringify({
      reason_category: reasonCategory,
      description,
    }),
  });
}

export async function getBookingDispute(
  bookingId: string,
): Promise<Dispute | null> {
  return apiFetch<Dispute | null>(`/bookings/${bookingId}/dispute`);
}
