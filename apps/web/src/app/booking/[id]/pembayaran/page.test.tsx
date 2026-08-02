import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { QueryProvider } from "@/lib/query-provider";

import PaymentPage from "./page";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "b1" }),
  useRouter: () => ({ push }),
}));

const CLIENT = {
  id: "u1",
  email: "klien@jepret.local",
  full_name: "Klien Demo",
  is_admin: false,
  creator_profile: null,
};

const CREATOR = {
  ...CLIENT,
  id: "u2",
  creator_profile: {
    id: "c1",
    display_name: "Studio Cahaya",
    city: "Bandung",
    bio: "Dokumentasi hangat.",
    specialty: "wedding",
    starting_price_idr: 1_500_000,
    status: "approved",
    submitted_at: null,
    reviewed_at: null,
  },
};

function booking(status = "accepted") {
  return {
    id: "b1",
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

function payment(status = "pending") {
  return {
    id: "p1",
    booking_id: "b1",
    provider: "mock",
    amount_idr: 1_500_000,
    platform_fee_idr: 150_000,
    creator_net_idr: 1_350_000,
    status,
    paid_at: null,
    held_at: null,
    released_at: null,
    refunded_at: null,
    created_at: "2026-07-31T00:00:00Z",
  };
}

type MockResponse = {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
};

function response(data: unknown, status = 200): MockResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () =>
      Promise.resolve(
        status >= 400
          ? { error: { code: "TEST_ERROR", message: "Test error" } }
          : { data },
      ),
  };
}

function stubPage({
  me = CLIENT,
  bookings = [booking()],
  incoming = [],
  paymentResult = response(null, 404),
}: {
  me?: typeof CLIENT | typeof CREATOR | null;
  bookings?: unknown[];
  incoming?: unknown[];
  paymentResult?: MockResponse | Promise<MockResponse>;
} = {}) {
  const fetchMock = vi.fn((url: string, _init?: RequestInit) => {
    if (url.endsWith("/auth/me")) return Promise.resolve(response(me));
    if (url.endsWith("/bookings/incoming"))
      return Promise.resolve(response(incoming));
    if (url.endsWith("/bookings")) return Promise.resolve(response(bookings));
    if (url.endsWith("/bookings/b1/payments"))
      return Promise.resolve(paymentResult);
    return Promise.resolve(response(payment()));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPage() {
  return render(
    <QueryProvider>
      <PaymentPage />
    </QueryProvider>,
  );
}

afterEach(() => {
  push.mockClear();
  vi.unstubAllGlobals();
});

describe("PaymentPage", () => {
  it("creates one payment with a stable UUID idempotency key", async () => {
    let resolveCreate!: (value: MockResponse) => void;
    const createResult = new Promise<MockResponse>((resolve) => {
      resolveCreate = resolve;
    });
    let createRequests = 0;
    const fetchMock = stubPage();
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/me")) return Promise.resolve(response(CLIENT));
      if (url.endsWith("/bookings/incoming"))
        return Promise.resolve(response([]));
      if (url.endsWith("/bookings"))
        return Promise.resolve(response([booking()]));
      if (url.endsWith("/bookings/b1/payments") && init?.method === "POST") {
        createRequests += 1;
        return createRequests === 1
          ? Promise.resolve(response(null, 500))
          : createResult;
      }
      return Promise.resolve(response(null, 404));
    });
    const view = renderPage();

    expect(await screen.findByText(/Rp\s*1\.500\.000/)).toBeVisible();
    expect(
      screen.getByText(
        "Pembayaran simulasi — tidak ada dana nyata yang diproses.",
      ),
    ).toBeVisible();
    const button = screen.getByRole("button", { name: "Buat pembayaran" });
    await userEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Aksi pembayaran belum berhasil. Silakan coba lagi.",
    );
    view.rerender(
      <QueryProvider>
        <PaymentPage />
      </QueryProvider>,
    );
    await userEvent.click(button);
    expect(button).toBeDisabled();
    await userEvent.click(button);

    const creates = fetchMock.mock.calls.filter(
      ([url, init]) =>
        String(url).endsWith("/bookings/b1/payments") &&
        (init as RequestInit | undefined)?.method === "POST",
    );
    expect(creates).toHaveLength(2);
    const keys = creates.map(([, init]) =>
      new Headers((init as RequestInit).headers).get("Idempotency-Key"),
    );
    expect(new Set(keys)).toHaveProperty("size", 1);
    const key = keys[0];
    expect(key).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
    resolveCreate(response(payment()));
  });

  it("simulates a pending payment once while the request is pending", async () => {
    let resolvePaid!: (value: MockResponse) => void;
    const paidResult = new Promise<MockResponse>((resolve) => {
      resolvePaid = resolve;
    });
    const fetchMock = stubPage({ paymentResult: response(payment()) });
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/me")) return Promise.resolve(response(CLIENT));
      if (url.endsWith("/bookings/incoming"))
        return Promise.resolve(response([]));
      if (url.endsWith("/bookings"))
        return Promise.resolve(response([booking("awaiting_payment")]));
      if (url.endsWith("/bookings/b1/payments"))
        return Promise.resolve(response(payment()));
      if (url.endsWith("/dev/payments/p1/simulate-paid")) return paidResult;
      return Promise.resolve(response(null, 404));
    });
    renderPage();

    const button = await screen.findByRole("button", {
      name: "Simulasikan pembayaran berhasil",
    });
    await userEvent.click(button);
    expect(button).toBeDisabled();
    await userEvent.click(button);
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith("/dev/payments/p1/simulate-paid"),
      ),
    ).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/dev/payments/p1/simulate-paid",
      expect.objectContaining({ method: "POST" }),
    );
    resolvePaid(response(payment("held")));
  });

  it("allows only the related creator to release a held completed booking", async () => {
    const fetchMock = stubPage({
      me: CREATOR,
      bookings: [],
      incoming: [booking("completed")],
      paymentResult: response(payment("held")),
    });
    renderPage();
    await userEvent.click(
      await screen.findByRole("button", { name: "Simulasikan pencairan" }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/dev/payments/p1/simulate-release",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it.each([
    [CLIENT, "completed", "held"],
    [CREATOR, "confirmed", "held"],
    [CREATOR, "completed", "paid"],
  ])(
    "hides release for an unauthorized user or wrong state",
    async (me, bookingStatus, paymentStatus) => {
      stubPage({
        me,
        bookings: me.creator_profile ? [] : [booking(bookingStatus)],
        incoming: me.creator_profile ? [booking(bookingStatus)] : [],
        paymentResult: response(payment(paymentStatus)),
      });
      renderPage();
      await screen.findByText(
        "Pembayaran simulasi — tidak ada dana nyata yang diproses.",
      );
      expect(
        screen.queryByRole("button", { name: "Simulasikan pencairan" }),
      ).not.toBeInTheDocument();
    },
  );

  it.each([
    ["pending", "Menunggu pembayaran"],
    ["paid", "Pembayaran diterima"],
    ["held", "Dana tercatat aman"],
    ["released", "Pembayaran telah dilepas"],
    ["refunded", "Pembayaran dikembalikan"],
    ["failed", "Pembayaran gagal"],
    ["expired", "Pembayaran kedaluwarsa"],
  ])("shows exact %s payment status copy", async (status, label) => {
    stubPage({ paymentResult: response(payment(status)) });
    renderPage();
    expect(await screen.findByText(label)).toBeVisible();
  });

  it("redirects unauthenticated users to sign in", async () => {
    stubPage({ me: null });
    renderPage();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/masuk"));
  });

  it("shows booking and payment loading states in sequence", async () => {
    let resolveBookings!: (value: MockResponse) => void;
    let resolvePayment!: (value: MockResponse) => void;
    const bookingsResult = new Promise<MockResponse>((resolve) => {
      resolveBookings = resolve;
    });
    const paymentResult = new Promise<MockResponse>((resolve) => {
      resolvePayment = resolve;
    });
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/auth/me")) return Promise.resolve(response(CLIENT));
      if (url.endsWith("/bookings/incoming"))
        return Promise.resolve(response([]));
      if (url.endsWith("/bookings")) return bookingsResult;
      return paymentResult;
    });
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderPage();

    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes("payments")),
    ).toBe(false);
    resolveBookings(response([booking()]));
    expect(await screen.findByText("Memuat pembayaran…")).toBeVisible();
    resolvePayment(response(null, 404));
  });

  it("treats a payment 404 as not yet created", async () => {
    stubPage();
    renderPage();
    expect(await screen.findByText("Pembayaran belum dibuat")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a retryable booking error", async () => {
    let requests = 0;
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/auth/me")) return Promise.resolve(response(CLIENT));
      if (url.endsWith("/bookings/incoming"))
        return Promise.resolve(response([]));
      if (url.endsWith("/bookings")) {
        requests += 1;
        return Promise.resolve(
          requests === 1 ? response(null, 500) : response([booking()]),
        );
      }
      return Promise.resolve(response(null, 404));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Booking belum dapat dimuat. Silakan coba lagi.",
    );
    await userEvent.click(screen.getByRole("button", { name: "Coba lagi" }));
    expect(await screen.findByText("Pembayaran belum dibuat")).toBeVisible();
  });

  it("shows a retryable payment error", async () => {
    let requests = 0;
    const fetchMock = stubPage();
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith("/auth/me")) return Promise.resolve(response(CLIENT));
      if (url.endsWith("/bookings/incoming"))
        return Promise.resolve(response([]));
      if (url.endsWith("/bookings"))
        return Promise.resolve(response([booking()]));
      requests += 1;
      return Promise.resolve(
        requests === 1 ? response(null, 500) : response(payment()),
      );
    });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Pembayaran belum dapat dimuat. Silakan coba lagi.",
    );
    await userEvent.click(screen.getByRole("button", { name: "Coba lagi" }));
    expect(await screen.findByText("Menunggu pembayaran")).toBeVisible();
  });

  it("handles an empty or unrelated booking", async () => {
    stubPage({ bookings: [{ ...booking(), id: "other" }] });
    renderPage();
    expect(await screen.findByText("Booking tidak ditemukan.")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Buat pembayaran" }),
    ).not.toBeInTheDocument();
  });
});
