import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { QueryProvider } from "@/lib/query-provider";

import BookingMasukPage from "./page";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

const ME = {
  id: "u2",
  email: "kreator@jepret.local",
  full_name: "Kreator Demo",
  is_admin: false,
  creator_profile: { id: "c1", status: "approved" },
};

function incoming(status: string, id = "b9") {
  return [
    {
      id,
      status,
      event_date: "2026-09-10",
      event_city: "Bandung",
      notes: "",
      quoted_price_idr: 1_500_000,
      created_at: "2026-07-21T00:00:00Z",
      started_at: null,
      delivered_at: null,
      completed_at: null,
      creator: {
        id: "c1",
        display_name: "Studio Cahaya",
        city: "Bandung",
        specialty: "wedding",
      },
      client_name: "Klien Demo",
    },
  ];
}

function stubFetch(bookings: unknown[], unread: unknown[] = []) {
  const fetchMock = vi.fn((url: string) => {
    if (url.includes("/auth/me")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ data: ME }),
      });
    }
    if (url.includes("/conversations/unread")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ data: unread }),
      });
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ data: bookings }),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPage() {
  return render(
    <QueryProvider>
      <BookingMasukPage />
    </QueryProvider>,
  );
}

afterEach(() => {
  push.mockClear();
  vi.unstubAllGlobals();
});

describe("BookingMasukPage", () => {
  it("accepts a requested booking", async () => {
    const fetchMock = stubFetch(incoming("requested"));
    renderPage();
    expect(await screen.findByText("Klien Demo")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Terima" }));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/bookings/b9/accept",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it.each(["confirmed", "in_progress", "delivered", "completed"])(
    "offers workspace and payment links for %s bookings without a direct completion button",
    async (status) => {
      stubFetch(incoming(status));
      renderPage();
      expect(
        await screen.findByRole("link", { name: "Buka ruang kerja" }),
      ).toHaveAttribute("href", "/booking/b9");
      expect(
        screen.getByRole("link", { name: "Lihat pembayaran" }),
      ).toHaveAttribute("href", "/booking/b9/pembayaran");
      expect(
        screen.queryByRole("button", { name: "Tandai selesai" }),
      ).not.toBeInTheDocument();
    },
  );

  it("shows unread badge on matching creator booking card", async () => {
    stubFetch(incoming("confirmed", "b9"), [{ booking_id: "b9", count: 2 }]);
    renderPage();
    const badge = await screen.findByLabelText("2 pesan belum dibaca");
    expect(badge).toBeVisible();
    expect(badge).toHaveTextContent("2");
  });

  it("shows awaiting payment without creator action buttons", async () => {
    stubFetch(incoming("awaiting_payment"));
    renderPage();
    expect(await screen.findByText("Menunggu pembayaran")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Tandai selesai" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Buka ruang kerja" }),
    ).not.toBeInTheDocument();
  });
});
