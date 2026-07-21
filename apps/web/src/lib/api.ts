export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.code = body.code;
    this.status = status;
  }
}

export interface CreatorProfile {
  id: string;
  display_name: string;
  city: string;
  bio: string;
  specialty: string;
  starting_price_idr: number;
  status: "draft" | "pending" | "approved" | "rejected";
  submitted_at: string | null;
  reviewed_at: string | null;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_admin: boolean;
  creator_profile: CreatorProfile | null;
}

interface Envelope<T> {
  data: T;
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...init.headers },
    ...init,
  });

  const payload = (await response.json().catch(() => null)) as
    Envelope<T> | { error: ApiErrorBody } | null;

  if (!response.ok) {
    const body =
      payload && "error" in payload
        ? payload.error
        : { code: "UNKNOWN_ERROR", message: "Terjadi kesalahan tak terduga." };
    throw new ApiError(response.status, body);
  }

  return (payload as Envelope<T>).data;
}

export interface CreatorPublic {
  id: string;
  display_name: string;
  city: string;
  bio: string;
  specialty: string;
  starting_price_idr: number;
}

export interface CreatorListPage {
  items: CreatorPublic[];
  next_cursor: string | null;
}
