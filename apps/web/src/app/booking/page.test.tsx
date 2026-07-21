import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { QueryProvider } from "@/lib/query-provider";

import BookingPage from "./page";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

const ME = {
  id: "u1",
  email: "klien@jepret.local",
  full_name: "Klien Demo",
  is_admin: false,
  creator_profile: null,
};

function booking(id: string, status: string) {
  return {
    id,
    status,
    event_date: "2026-09-01",
    event_city: "Bandung",
    notes: "Akad pagi.",
    quoted_price_idr: 1_500_000,
    created_at: "2026-07-21T00:00:00Z",
    creator: {
      id: "c1",
      display_name: "Studio Cahaya",
      city: "Bandung",
      specialty: "wedding",
    },
    client_name: "Klien Demo",
  };
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
      <BookingPage />
    </QueryProvider>,
  );
}

afterEach(() => {
  push.mockClear();
  vi.unstubAllGlobals();
});

describe("BookingPage", () => {
  it("lists bookings with a status label", async () => {
    stubFetch([booking("b1", "requested")]);
    renderPage();
    expect(await screen.findByText("Studio Cahaya")).toBeVisible();
    expect(screen.getByText("Menunggu konfirmasi")).toBeVisible();
    expect(screen.getByText(/2026-09-01 · Bandung/)).toBeVisible();
  });

  it("cancels an active booking", async () => {
    const fetchMock = stubFetch([booking("b1", "accepted")]);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Batalkan" }));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/bookings/b1/cancel",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("hides cancel for terminal bookings and shows empty state", async () => {
    stubFetch([]);
    renderPage();
    expect(await screen.findByText("Belum ada booking.")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Batalkan" }),
    ).not.toBeInTheDocument();
  });
});
