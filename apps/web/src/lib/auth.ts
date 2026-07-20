"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import { ApiError, apiFetch, type CreatorProfile, type User } from "./api";

export const ME_QUERY_KEY = ["auth", "me"] as const;

async function fetchMe(): Promise<User | null> {
  try {
    return await apiFetch<User>("/auth/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export function useMe(): UseQueryResult<User | null> {
  return useQuery({ queryKey: ME_QUERY_KEY, queryFn: fetchMe, retry: 0 });
}

interface Credentials {
  email: string;
  password: string;
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Credentials) =>
      apiFetch<User>("/auth/login", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: (user) => queryClient.setQueryData(ME_QUERY_KEY, user),
  });
}

export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Credentials & { full_name: string }) =>
      apiFetch<User>("/auth/register", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: (user) => queryClient.setQueryData(ME_QUERY_KEY, user),
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<{ status: string }>("/auth/logout", { method: "POST" }),
    onSuccess: () => queryClient.setQueryData(ME_QUERY_KEY, null),
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { full_name: string }) =>
      apiFetch<User>("/profiles/me", {
        method: "PATCH",
        body: JSON.stringify(input),
      }),
    onSuccess: (user) => queryClient.setQueryData(ME_QUERY_KEY, user),
  });
}

export interface CreatorDraftInput {
  display_name: string;
  city: string;
  bio: string;
  specialty: string;
  starting_price_idr: number;
}

export function useSaveCreatorDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreatorDraftInput) =>
      apiFetch<CreatorProfile>("/profiles/me/creator", {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
  });
}

export function useSubmitCreatorProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<CreatorProfile>("/profiles/me/creator/submit", {
        method: "POST",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
  });
}
