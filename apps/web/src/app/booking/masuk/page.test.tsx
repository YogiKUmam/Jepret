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

function incoming(status: string) {
  return [
    {
      id: "b9",
      status,
      event_date: "2026-09-10",
      event_city: "Bandung",
      notes: "",
      quoted_price_idr: 1_500_000,
      created_at: "2026-07-21T00:00:00Z",
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

function stubFetch(bookings: unknown[]) {
  const fetchMock = vi.fn((url: string) => {
    const body = url.includes("/auth/me") ? { data: ME } : { data: bookings };
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
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

  it("offers completion and payment details for confirmed bookings", async () => {
    stubFetch(incoming("confirmed"));
    renderPage();
    expect(
      await screen.findByRole("button", { name: "Tandai selesai" }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Lihat pembayaran" }),
    ).toHaveAttribute("href", "/booking/b9/pembayaran");
    expect(
      screen.queryByRole("button", { name: "Terima" }),
    ).not.toBeInTheDocument();
  });

  it("keeps payment details available for completed bookings", async () => {
    stubFetch(incoming("completed"));
    renderPage();
    expect(
      await screen.findByRole("link", { name: "Lihat pembayaran" }),
    ).toHaveAttribute("href", "/booking/b9/pembayaran");
    expect(
      screen.queryByRole("button", { name: "Tandai selesai" }),
    ).not.toBeInTheDocument();
  });

  it("shows awaiting payment without creator actions", async () => {
    stubFetch(incoming("awaiting_payment"));
    renderPage();
    expect(await screen.findByText("Menunggu pembayaran")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Tandai selesai" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Lihat pembayaran" }),
    ).not.toBeInTheDocument();
  });
});
