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
  const { headers, ...requestInit } = init;
  const normalizedHeaders = new Headers(headers);
  if (!normalizedHeaders.has("Content-Type")) {
    normalizedHeaders.set("Content-Type", "application/json");
  }
  const response = await fetch(`/api/v1${path}`, {
    ...requestInit,
    credentials: "same-origin",
    headers: normalizedHeaders,
  });

  if (response.status === 204) return undefined as T;

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

export type BookingStatus =
  | "requested"
  | "accepted"
  | "awaiting_payment"
  | "confirmed"
  | "in_progress"
  | "delivered"
  | "rejected"
  | "completed"
  | "cancelled";

export type PaymentStatus =
  "pending" | "paid" | "held" | "released" | "refunded" | "failed" | "expired";

export interface Payment {
  id: string;
  booking_id: string;
  provider: "mock";
  amount_idr: number;
  platform_fee_idr: number;
  creator_net_idr: number;
  status: PaymentStatus;
  paid_at: string | null;
  held_at: string | null;
  released_at: string | null;
  refunded_at: string | null;
  created_at: string;
}

export interface BookingCreator {
  id: string;
  display_name: string;
  city: string;
  specialty: string;
}

export interface Booking {
  id: string;
  status: BookingStatus;
  event_date: string;
  event_city: string;
  notes: string;
  quoted_price_idr: number;
  created_at: string;
  started_at: string | null;
  delivered_at: string | null;
  completed_at: string | null;
  creator: BookingCreator;
  client_name: string;
}

export interface Conversation {
  id: string;
  booking_id: string;
  created_at: string;
}

export interface MessageAttachment {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
}

export interface MessageSender {
  id: string;
  full_name: string;
}

export interface Message {
  id: string;
  client_message_id: string;
  message_type: "text" | "attachment" | "system";
  body: string | null;
  attachment: MessageAttachment | null;
  sender: MessageSender;
  read_at: string | null;
  created_at: string;
}

export interface MessagePage {
  items: Message[];
  next_cursor: string | null;
}

export type UploadPurpose = "chat_attachment" | "deliverable";
export type UploadContentType =
  | "image/jpeg"
  | "image/png"
  | "image/webp"
  | "application/pdf"
  | "application/zip";
export type UploadStatus = "pending" | "completed" | "expired" | "rejected";

export interface Upload {
  id: string;
  purpose: UploadPurpose;
  filename: string;
  content_type: UploadContentType;
  size_bytes: number;
  status: UploadStatus;
  completed_at: string | null;
  expires_at: string;
}

export interface UploadIntent extends Upload {
  upload_url: string;
  required_headers: Record<string, string>;
}

export interface Deliverable {
  id: string;
  booking_id: string;
  uploaded_by_user_id: string;
  title: string;
  description: string | null;
  source_type: "private_file" | "external_link";
  upload_id: string | null;
  external_url: string | null;
  external_host: string | null;
  media_type: string | null;
  filename: string | null;
  content_type: string | null;
  size_bytes: number | null;
  replaces_deliverable_id: string | null;
  downloadable: boolean;
  created_at: string;
}

export interface WorkspacePayment {
  id: string;
  status: PaymentStatus;
  amount_idr: number;
  platform_fee_idr: number;
  creator_net_idr: number;
  paid_at: string | null;
  held_at: string | null;
  released_at: string | null;
  refunded_at: string | null;
}

export interface Workspace {
  role: "client" | "creator";
  booking: Booking;
  conversation: Conversation | null;
  deliverables: Deliverable[];
  unread_count: number;
  payment: WorkspacePayment | null;
}
