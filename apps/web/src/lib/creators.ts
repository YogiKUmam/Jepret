"use client";

import {
  useInfiniteQuery,
  useQuery,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  ApiError,
  apiFetch,
  type CreatorListPage,
  type CreatorPublic,
} from "./api";

export interface CreatorFilters {
  q?: string;
  city?: string;
  specialty?: string;
  min_price?: number;
  max_price?: number;
}

export function creatorListPath(
  filters: CreatorFilters,
  cursor?: string,
): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  if (cursor) params.set("cursor", cursor);
  const query = params.toString();
  return query ? `/creators?${query}` : "/creators";
}

export function useCreatorsInfinite(filters: CreatorFilters) {
  return useInfiniteQuery({
    queryKey: ["creators", "list", filters],
    queryFn: ({ pageParam }) =>
      apiFetch<CreatorListPage>(
        creatorListPath(filters, pageParam ?? undefined),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
  });
}

async function fetchCreator(id: string): Promise<CreatorPublic | null> {
  try {
    return await apiFetch<CreatorPublic>(`/creators/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function useCreator(id: string): UseQueryResult<CreatorPublic | null> {
  return useQuery({
    queryKey: ["creators", "detail", id],
    queryFn: () => fetchCreator(id),
    retry: 0,
  });
}
