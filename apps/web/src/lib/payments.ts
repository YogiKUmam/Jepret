"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, type Payment } from "./api";
import { BOOKINGS_KEY, INCOMING_KEY } from "./bookings";

export const paymentKey = (bookingId: string) =>
  ["payments", bookingId] as const;

export function usePayment(bookingId: string) {
  return useQuery({
    queryKey: paymentKey(bookingId),
    queryFn: () => apiFetch<Payment>(`/bookings/${bookingId}/payments`),
    retry: false,
  });
}

export function useCreatePayment(bookingId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (idempotencyKey: string) =>
      apiFetch<Payment>(`/bookings/${bookingId}/payments`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
      }),
    onSuccess: (payment) => {
      queryClient.setQueryData(paymentKey(bookingId), payment);
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: paymentKey(bookingId) }),
        queryClient.invalidateQueries({ queryKey: BOOKINGS_KEY }),
        queryClient.invalidateQueries({ queryKey: INCOMING_KEY }),
      ]);
    },
  });
}

function useSimulatePayment(
  action: "simulate-paid" | "simulate-release",
  paymentId: string,
  bookingId: string,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      apiFetch<Payment>(`/dev/payments/${paymentId}/${action}`, {
        method: "POST",
      }),
    onSuccess: (payment) => {
      queryClient.setQueryData(paymentKey(bookingId), payment);
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: paymentKey(bookingId) }),
        queryClient.invalidateQueries({ queryKey: BOOKINGS_KEY }),
        queryClient.invalidateQueries({ queryKey: INCOMING_KEY }),
      ]);
    },
  });
}

export function useSimulatePaid(paymentId: string, bookingId: string) {
  return useSimulatePayment("simulate-paid", paymentId, bookingId);
}

export function useSimulateRelease(paymentId: string, bookingId: string) {
  return useSimulatePayment("simulate-release", paymentId, bookingId);
}
