import {
  AdminOverview,
  apiFetch,
  CreatorApplication,
  CreatorProfile,
  Dispute,
} from "./api";

export async function getAdminOverview(): Promise<AdminOverview> {
  return apiFetch<AdminOverview>("/admin/overview");
}

export async function listAdminDisputes(
  status?: string | null,
): Promise<Dispute[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const queryString = params.toString();
  return apiFetch<Dispute[]>(
    `/admin/disputes${queryString ? `?${queryString}` : ""}`,
  );
}

export async function resolveAdminDispute(
  disputeId: string,
  resolution: "resolved_client" | "resolved_creator",
  resolutionNotes: string,
): Promise<Dispute> {
  return apiFetch<Dispute>(`/admin/disputes/${disputeId}/resolve`, {
    method: "POST",
    body: JSON.stringify({
      resolution,
      resolution_notes: resolutionNotes,
    }),
  });
}

export async function listCreatorApplications(): Promise<CreatorApplication[]> {
  return apiFetch<CreatorApplication[]>("/admin/creator-applications");
}

export async function approveCreatorApplication(
  profileId: string,
): Promise<CreatorProfile> {
  return apiFetch<CreatorProfile>(
    `/admin/creator-applications/${profileId}/approve`,
    {
      method: "POST",
    },
  );
}

export async function rejectCreatorApplication(
  profileId: string,
): Promise<CreatorProfile> {
  return apiFetch<CreatorProfile>(
    `/admin/creator-applications/${profileId}/reject`,
    {
      method: "POST",
    },
  );
}
