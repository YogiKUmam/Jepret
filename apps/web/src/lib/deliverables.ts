"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, type Deliverable } from "./api";
import { workspaceKey } from "./workspaces";

export const deliverablesKey = (bookingId: string) =>
  ["deliverables", bookingId] as const;

export type CreateDeliverableInput =
  | {
      source_type: "private_file";
      title: string;
      description?: string | null;
      replaces_deliverable_id?: string | null;
      upload_id: string;
    }
  | {
      source_type: "external_link";
      title: string;
      description?: string | null;
      replaces_deliverable_id?: string | null;
      external_url: string;
    };

export function useDeliverables(bookingId: string) {
  return useQuery({
    queryKey: deliverablesKey(bookingId),
    queryFn: () =>
      apiFetch<Deliverable[]>(`/bookings/${bookingId}/deliverables`),
    retry: false,
  });
}

export function useCreateDeliverable(bookingId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateDeliverableInput) =>
      apiFetch<Deliverable>(`/bookings/${bookingId}/deliverables`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({
          queryKey: deliverablesKey(bookingId),
          exact: true,
        }),
        queryClient.invalidateQueries({
          queryKey: workspaceKey(bookingId),
          exact: true,
        }),
      ]),
  });
}

export function useDeleteDeliverable(bookingId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (deliverableId: string) =>
      apiFetch<void>(`/deliverables/${deliverableId}`, { method: "DELETE" }),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({
          queryKey: deliverablesKey(bookingId),
          exact: true,
        }),
        queryClient.invalidateQueries({
          queryKey: workspaceKey(bookingId),
          exact: true,
        }),
      ]),
  });
}

export function requestPrivateDownload(
  uploadId: string,
): Promise<{ url: string }> {
  return apiFetch<{ url: string }>(`/uploads/${uploadId}/download`, {
    method: "POST",
  });
}
