import { render, screen, waitFor } from "@testing-library/react";
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
  };
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

  it("cancels an active booking before work starts", async () => {
    const fetchMock = stubFetch([booking("b1", "accepted")]);
    renderPage();
    await userEvent.click(
      await screen.findByRole("button", { name: "Batalkan" }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/bookings/b1/cancel",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("reports a cancellation failure and allows retry", async () => {
    type MockResponse = {
      ok: boolean;
      status: number;
      json: () => Promise<unknown>;
    };
    let resolveCancel!: (response: MockResponse) => void;
    const cancelResponse = new Promise<MockResponse>((resolve) => {
      resolveCancel = resolve;
    });
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
          json: () => Promise.resolve({ data: [] }),
        });
      }
      if (url.endsWith("/bookings/b1/cancel")) return cancelResponse;
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ data: [booking("b1", "confirmed")] }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    const cancelButton = await screen.findByRole("button", {
      name: "Batalkan",
    });
    await userEvent.click(cancelButton);
    expect(cancelButton).toBeDisabled();
    await userEvent.click(cancelButton);
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith("/bookings/b1/cancel"),
      ),
    ).toHaveLength(1);

    resolveCancel({
      ok: false,
      status: 409,
      json: () =>
        Promise.resolve({
          error: {
            code: "INVALID_BOOKING_STATE",
            message: "Booking tidak dapat dibatalkan.",
          },
        }),
    });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "Booking belum dapat dibatalkan. Silakan coba lagi.",
    );
    expect(alert).toHaveClass("text-[var(--surface-foreground)]");
    expect(cancelButton).toBeEnabled();
    await userEvent.click(cancelButton);
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(([url]) =>
          String(url).endsWith("/bookings/b1/cancel"),
        ),
      ),
    );
  });

  it("links accepted bookings to payment creation", async () => {
    stubFetch([booking("b1", "accepted")]);
    renderPage();
    const paymentLink = await screen.findByRole("link", {
      name: "Bayar sekarang",
    });
    expect(paymentLink).toHaveAttribute("href", "/booking/b1/pembayaran");
  });

  it.each(["confirmed", "in_progress", "delivered", "completed"])(
    "links %s bookings to workspace",
    async (status) => {
      stubFetch([booking("b1", status)]);
      renderPage();
      const workspaceLink = await screen.findByRole("link", {
        name: "Buka ruang kerja",
      });
      expect(workspaceLink).toHaveAttribute("href", "/booking/b1");
    },
  );

  it.each(["in_progress", "delivered", "completed"])(
    "hides cancel button once work starts in %s status",
    async (status) => {
      stubFetch([booking("b1", status)]);
      renderPage();
      await screen.findByText("Studio Cahaya");
      expect(
        screen.queryByRole("button", { name: "Batalkan" }),
      ).not.toBeInTheDocument();
    },
  );

  it("shows unread badge on matching booking card when unread count > 0", async () => {
    stubFetch(
      [booking("b1", "confirmed"), booking("b2", "confirmed")],
      [{ booking_id: "b1", count: 3 }],
    );
    renderPage();
    const badge = await screen.findByLabelText("3 pesan belum dibaca");
    expect(badge).toBeVisible();
    expect(badge).toHaveTextContent("3");
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
