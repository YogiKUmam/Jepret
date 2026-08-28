"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, type Booking, type BookingStatus } from "./api";

export const BOOKINGS_KEY = ["bookings", "mine"] as const;
export const INCOMING_KEY = ["bookings", "incoming"] as const;

export const BOOKING_STATUS_LABELS: Record<BookingStatus, string> = {
  requested: "Menunggu konfirmasi",
  accepted: "Diterima",
  awaiting_payment: "Menunggu pembayaran",
  confirmed: "Terkonfirmasi",
  in_progress: "Sedang berlangsung",
  delivered: "Hasil dikirim",
  rejected: "Ditolak",
  completed: "Selesai",
  cancelled: "Dibatalkan",
  disputed: "Dalam sengketa",
};

export const ACTIVE_BOOKING_STATUSES: BookingStatus[] = [
  "requested",
  "accepted",
  "awaiting_payment",
  "confirmed",
  "in_progress",
  "delivered",
];

export interface CreateBookingInput {
  creator_id: string;
  event_date: string;
  event_city: string;
  notes: string;
}

export function useMyBookings() {
  return useQuery({
    queryKey: BOOKINGS_KEY,
    queryFn: () => apiFetch<Booking[]>("/bookings"),
    retry: 0,
  });
}

export function useIncomingBookings() {
  return useQuery({
    queryKey: INCOMING_KEY,
    queryFn: () => apiFetch<Booking[]>("/bookings/incoming"),
    retry: 0,
  });
}

export function useCreateBooking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateBookingInput) =>
      apiFetch<Booking>("/bookings", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: BOOKINGS_KEY }),
  });
}

type BookingAction =
  "accept" | "reject" | "start" | "deliver" | "complete" | "cancel";

export function useBookingAction(action: BookingAction) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (bookingId: string) =>
      apiFetch<Booking>(`/bookings/${bookingId}/${action}`, { method: "POST" }),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: BOOKINGS_KEY }),
        queryClient.invalidateQueries({ queryKey: INCOMING_KEY }),
      ]),
  });
}
