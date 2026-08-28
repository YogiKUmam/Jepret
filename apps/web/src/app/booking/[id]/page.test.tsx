import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Deliverable, Message, Workspace } from "@/lib/api";
import { QueryProvider } from "@/lib/query-provider";

import WorkspacePage from "./page";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "b1" }),
  useRouter: () => ({ push }),
}));

const CLIENT_USER = {
  id: "u1",
  email: "klien@jepret.local",
  full_name: "Klien Demo",
  is_admin: false,
  creator_profile: null,
};

const CREATOR_USER = {
  id: "u2",
  email: "kreator@jepret.local",
  full_name: "Kreator Demo",
  is_admin: false,
  creator_profile: {
    id: "c1",
    display_name: "Studio Cahaya",
    city: "Bandung",
    specialty: "wedding",
    starting_price_idr: 1_500_000,
    status: "approved",
  },
};

function sampleWorkspace(
  role: "client" | "creator" = "creator",
  status:
    | "confirmed"
    | "in_progress"
    | "delivered"
    | "completed"
    | "cancelled" = "confirmed",
  overrides: Partial<Workspace> = {},
): Workspace {
  return {
    role,
    booking: {
      id: "b1",
      status,
      event_date: "2026-09-01",
      event_city: "Bandung",
      notes: "Foto outdoor.",
      quoted_price_idr: 1_500_000,
      created_at: "2026-07-21T00:00:00Z",
      started_at:
        status === "in_progress" ||
        status === "delivered" ||
        status === "completed"
          ? "2026-08-01T10:00:00Z"
          : null,
      delivered_at:
        status === "delivered" || status === "completed"
          ? "2026-08-02T10:00:00Z"
          : null,
      completed_at: status === "completed" ? "2026-08-03T10:00:00Z" : null,
      creator: {
        id: "c1",
        display_name: "Studio Cahaya",
        city: "Bandung",
        specialty: "wedding",
      },
      client_name: "Klien Demo",
    },
    conversation: {
      id: "conv-1",
      booking_id: "b1",
      created_at: "2026-07-21T00:00:00Z",
    },
    deliverables: [],
    unread_count: 0,
    payment: {
      id: "p1",
      status: "held",
      amount_idr: 1_500_000,
      platform_fee_idr: 150_000,
      creator_net_idr: 1_350_000,
      paid_at: "2026-07-21T01:00:00Z",
      held_at: "2026-07-21T01:00:00Z",
      released_at: status === "completed" ? "2026-08-03T10:00:00Z" : null,
      refunded_at: null,
    },
    ...overrides,
  };
}

function sampleDeliverable(
  id: string,
  overrides: Partial<Deliverable> = {},
): Deliverable {
  return {
    id,
    booking_id: "b1",
    uploaded_by_user_id: "u2",
    title: "Foto Utama",
    description: "Hasil foto resolusi tinggi",
    source_type: "private_file",
    upload_id: "upl-1",
    external_url: null,
    external_host: null,
    media_type: "image/jpeg",
    filename: "foto-utama.jpg",
    content_type: "image/jpeg",
    size_bytes: 5_000_000,
    replaces_deliverable_id: null,
    downloadable: true,
    created_at: "2026-08-02T09:00:00Z",
    ...overrides,
  };
}

function sampleMessage(
  id = "11111111-1111-4111-8111-111111111111",
  body = "Halo!",
  overrides: Partial<Message> = {},
): Message {
  return {
    id,
    client_message_id: "22222222-2222-4222-8222-222222222222",
    message_type: "text",
    body,
    attachment: null,
    sender: {
      id: "33333333-3333-4333-8333-333333333333",
      full_name: "Klien Demo",
    },
    read_at: "2026-08-01T11:00:00Z",
    created_at: "2026-08-01T10:30:00Z",
    ...overrides,
  };
}

type FetchHandler = (
  url: string,
  init?: RequestInit,
) => Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }>;

function stubWorkspacePage({
  me = CREATOR_USER,
  workspace = sampleWorkspace(),
  messages = [sampleMessage("m1")],
  deliverables = [],
  customHandler,
}: {
  me?: unknown;
  workspace?: Workspace | null;
  messages?: Message[];
  deliverables?: Deliverable[];
  customHandler?: FetchHandler;
}) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (customHandler) {
      const custom = customHandler(url, init);
      if (custom) return custom;
    }
    if (url.endsWith("/auth/me")) {
      return Promise.resolve({
        ok: me !== null,
        status: me !== null ? 200 : 401,
        json: () => Promise.resolve({ data: me }),
      });
    }
    if (url.endsWith("/bookings/b1/workspace")) {
      return Promise.resolve({
        ok: workspace !== null,
        status: workspace !== null ? 200 : 404,
        json: () =>
          Promise.resolve(
            workspace !== null
              ? { data: workspace }
              : { error: { code: "NOT_FOUND", message: "Workspace tidak ditemukan." } },
          ),
      });
    }
    if (url.includes("/conversations/conv-1/messages")) {
      if (init?.method === "POST") {
        const parsed = JSON.parse(String(init.body ?? "{}"));
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              data: sampleMessage(
                "44444444-4444-4444-8444-444444444444",
                parsed.body ?? "",
                {
                  client_message_id:
                    parsed.client_message_id ??
                    "55555555-5555-4555-8555-555555555555",
                },
              ),
            }),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ data: { items: messages, next_cursor: null } }),
      });
    }
    if (url.includes("/conversations/conv-1/read")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ data: { count: 0, read_at: "2026-08-01T11:00:00Z" } }),
      });
    }
    if (url.endsWith("/bookings/b1/deliverables")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ data: deliverables }),
      });
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ data: null }),
    });
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderWorkspace() {
  return render(
    <QueryProvider>
      <WorkspacePage />
    </QueryProvider>,
  );
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  readonly url: string;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
}

beforeEach(() => {
  push.mockClear();
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("WorkspacePage", () => {
  it("redirects unauthenticated user to /masuk", async () => {
    stubWorkspacePage({ me: null });
    renderWorkspace();
    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/masuk");
    });
  });

  it("renders workspace header with booking details and accessible tabs", async () => {
    const user = userEvent.setup();
    stubWorkspacePage({
      me: CREATOR_USER,
      workspace: sampleWorkspace("creator", "confirmed"),
    });
    renderWorkspace();

    expect(await screen.findByText("Klien Demo")).toBeVisible();
    expect(screen.getByText(/1 September 2026/)).toBeVisible();
    expect(screen.getByText("Bandung")).toBeVisible();

    const chatTab = screen.getByRole("tab", { name: "Chat" });
    const deliverablesTab = screen.getByRole("tab", { name: "Hasil" });

    expect(chatTab).toHaveAttribute("aria-selected", "true");
    expect(deliverablesTab).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tabpanel", { name: "Chat" })).toBeVisible();

    await user.click(deliverablesTab);
    expect(deliverablesTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Hasil" })).toBeVisible();
  });

  it("supports keyboard arrow navigation between tabs", async () => {
    const user = userEvent.setup();
    stubWorkspacePage({
      me: CREATOR_USER,
      workspace: sampleWorkspace("creator", "confirmed"),
    });
    renderWorkspace();

    const chatTab = await screen.findByRole("tab", { name: "Chat" });
    const deliverablesTab = screen.getByRole("tab", { name: "Hasil" });

    chatTab.focus();
    expect(chatTab).toHaveFocus();

    await user.keyboard("{ArrowRight}");
    expect(deliverablesTab).toHaveFocus();
    expect(deliverablesTab).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{ArrowLeft}");
    expect(chatTab).toHaveFocus();
    expect(chatTab).toHaveAttribute("aria-selected", "true");
  });

  it("allows creator to start session when status is confirmed", async () => {
    const user = userEvent.setup();
    const fetchMock = stubWorkspacePage({
      me: CREATOR_USER,
      workspace: sampleWorkspace("creator", "confirmed"),
    });
    renderWorkspace();

    const startButton = await screen.findByRole("button", { name: "Mulai sesi" });
    expect(startButton).toBeEnabled();

    await user.click(startButton);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/bookings/b1/start",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("allows creator to deliver results when in_progress and deliverables exist", async () => {
    const user = userEvent.setup();
    const deliverable = sampleDeliverable("d1");
    const fetchMock = stubWorkspacePage({
      me: CREATOR_USER,
      workspace: sampleWorkspace("creator", "in_progress", {
        deliverables: [deliverable],
      }),
      deliverables: [deliverable],
    });
    renderWorkspace();

    const deliverButton = await screen.findByRole("button", { name: "Kirim hasil" });
    expect(deliverButton).toBeEnabled();

    await user.click(deliverButton);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/bookings/b1/deliver",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("disables deliver button for creator when in_progress but deliverables list is empty", async () => {
    stubWorkspacePage({
      me: CREATOR_USER,
      workspace: sampleWorkspace("creator", "in_progress", { deliverables: [] }),
      deliverables: [],
    });
    renderWorkspace();

    const deliverButton = await screen.findByRole("button", { name: "Kirim hasil" });
    expect(deliverButton).toBeDisabled();
  });

  it("shows client accept button with confirmation dialog when status is delivered", async () => {
    const user = userEvent.setup();
    const deliverable = sampleDeliverable("d1");
    const fetchMock = stubWorkspacePage({
      me: CLIENT_USER,
      workspace: sampleWorkspace("client", "delivered", {
        deliverables: [deliverable],
      }),
      deliverables: [deliverable],
    });
    renderWorkspace();

    const acceptButton = await screen.findByRole("button", { name: "Terima hasil" });
    expect(acceptButton).toBeEnabled();

    await user.click(acceptButton);

    // Confirmation dialog appears
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeVisible();
    expect(within(dialog).getByText(/Konfirmasi Penerimaan/i)).toBeVisible();
    expect(
      within(dialog).getByText(/pembayaran akan diteruskan ke kreator/i),
    ).toBeVisible();

    const confirmButton = within(dialog).getByRole("button", {
      name: "Ya, terima hasil",
    });
    await user.click(confirmButton);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/bookings/b1/complete",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("renders messages list and sends new text message", async () => {
    const user = userEvent.setup();
    const fetchMock = stubWorkspacePage({
      me: CLIENT_USER,
      workspace: sampleWorkspace("client", "confirmed"),
      messages: [
        sampleMessage(
          "11111111-1111-4111-8111-111111111111",
          "Halo, lokasi akad di mana?",
        ),
      ],
    });
    renderWorkspace();

    const input = await screen.findByPlaceholderText(/Tulis pesan…/i);
    fireEvent.change(input, { target: { value: "Lokasi di Gedung Sate" } });

    const sendButton = screen.getByRole("button", { name: "Kirim pesan" });
    await user.click(sendButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/conversations/conv-1/messages",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("Lokasi di Gedung Sate"),
        }),
      );
    });
  });

  it("displays external deliverable link with domain hostname", async () => {
    const user = userEvent.setup();
    const linkDeliverable = sampleDeliverable("d2", {
      source_type: "external_link",
      title: "Folder Google Drive",
      external_url: "https://drive.google.com/drive/folders/abc123xyz",
      external_host: "drive.google.com",
      media_type: null,
      filename: null,
      downloadable: false,
    });

    stubWorkspacePage({
      me: CLIENT_USER,
      workspace: sampleWorkspace("client", "delivered", {
        deliverables: [linkDeliverable],
      }),
      deliverables: [linkDeliverable],
    });
    renderWorkspace();

    const deliverablesTab = await screen.findByRole("tab", { name: "Hasil" });
    await user.click(deliverablesTab);

    expect(screen.getByText("Folder Google Drive")).toBeVisible();
    expect(screen.getByText("drive.google.com")).toBeVisible();
  });

  it("handles private file deliverable download authorization flow", async () => {
    const user = userEvent.setup();
    const fileDeliverable = sampleDeliverable("d1", {
      source_type: "private_file",
      title: "Foto Utama",
      upload_id: "upl-100",
      downloadable: true,
    });

    const openSpy = vi.fn();
    vi.stubGlobal("open", openSpy);

    const fetchMock = stubWorkspacePage({
      me: CLIENT_USER,
      workspace: sampleWorkspace("client", "delivered", {
        deliverables: [fileDeliverable],
      }),
      deliverables: [fileDeliverable],
      customHandler: (url, init) => {
        if (url.endsWith("/uploads/upl-100/download") && init?.method === "POST") {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ data: { url: "https://minio.local/signed-download" } }),
          });
        }
        return undefined as any;
      },
    });

    renderWorkspace();

    const deliverablesTab = await screen.findByRole("tab", { name: "Hasil" });
    await user.click(deliverablesTab);

    const downloadButton = screen.getByRole("button", { name: "Unduh berkas" });
    await user.click(downloadButton);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/uploads/upl-100/download",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
