"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, type Booking, type Workspace } from "./api";
import { BOOKINGS_KEY, INCOMING_KEY } from "./bookings";

export const workspaceKey = (bookingId: string) =>
  ["workspace", bookingId] as const;

export function useWorkspace(bookingId: string) {
  return useQuery({
    queryKey: workspaceKey(bookingId),
    queryFn: () => apiFetch<Workspace>(`/bookings/${bookingId}/workspace`),
    retry: false,
  });
}

export type WorkspaceAction = "start" | "deliver" | "complete";

export function useWorkspaceAction(bookingId: string, action: WorkspaceAction) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      apiFetch<Booking>(`/bookings/${bookingId}/${action}`, { method: "POST" }),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({
          queryKey: workspaceKey(bookingId),
          exact: true,
        }),
        queryClient.invalidateQueries({ queryKey: BOOKINGS_KEY, exact: true }),
        queryClient.invalidateQueries({ queryKey: INCOMING_KEY, exact: true }),
      ]),
  });
}
