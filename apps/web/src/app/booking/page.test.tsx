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
      ).toHaveLength(2),
    );
  });

  it("stays pending until cancellation refresh replaces stale actions", async () => {
    type MockResponse = {
      ok: boolean;
      status: number;
      json: () => Promise<unknown>;
    };
    let resolveRefetch!: (response: MockResponse) => void;
    const refetchResponse = new Promise<MockResponse>((resolve) => {
      resolveRefetch = resolve;
    });
    let bookingRequestCount = 0;
    const fetchMock = vi.fn((url: string) => {
      if (url.includes("/auth/me")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ data: ME }),
        });
      }
      if (url.endsWith("/bookings/b1/cancel")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ data: booking("b1", "cancelled") }),
        });
      }
      bookingRequestCount += 1;
      if (bookingRequestCount > 1) return refetchResponse;
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
    await waitFor(() => {
      expect(bookingRequestCount).toBe(2);
      expect(cancelButton).toBeDisabled();
    });
    await userEvent.click(cancelButton);
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith("/bookings/b1/cancel"),
      ),
    ).toHaveLength(1);

    resolveRefetch({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ data: [booking("b1", "cancelled")] }),
    });

    expect(await screen.findByText("Dibatalkan")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Batalkan" }),
    ).not.toBeInTheDocument();
  });

  it("links accepted bookings to payment creation", async () => {
    stubFetch([booking("b1", "accepted")]);
    renderPage();
    const paymentLink = await screen.findByRole("link", {
      name: "Bayar sekarang",
    });
    expect(paymentLink).toHaveAttribute("href", "/booking/b1/pembayaran");
    expect(paymentLink).toHaveClass("text-[var(--primary-foreground)]");
  });

  it.each(["awaiting_payment", "confirmed"])(
    "links %s bookings to payment details",
    async (status) => {
      stubFetch([booking("b1", status)]);
      renderPage();
      expect(
        await screen.findByRole("link", { name: "Lihat pembayaran" }),
      ).toHaveAttribute("href", "/booking/b1/pembayaran");
    },
  );

  it("hides cancel for terminal bookings and shows empty state", async () => {
    stubFetch([]);
    renderPage();
    expect(await screen.findByText("Belum ada booking.")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Batalkan" }),
    ).not.toBeInTheDocument();
  });
});
