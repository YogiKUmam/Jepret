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
  vi.unstubAllEnvs();
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

  it.each(["accepted", "completed", "cancelled"])(
    "hides simulate-paid when a pending payment belongs to a %s booking",
    async (status) => {
      const fetchMock = stubPage({
        bookings: [booking(status)],
        paymentResult: response(payment()),
      });
      renderPage();
      await screen.findByText("Menunggu pembayaran");
      expect(
        screen.queryByRole("button", {
          name: "Simulasikan pembayaran berhasil",
        }),
      ).not.toBeInTheDocument();
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).includes("simulate-paid"),
        ),
      ).toBe(false);
    },
  );

  it("hides development simulation controls in production but keeps creation", async () => {
    vi.stubEnv("NODE_ENV", "production");
    stubPage();
    const { unmount } = renderPage();
    expect(
      await screen.findByRole("button", { name: "Buat pembayaran" }),
    ).toBeVisible();
    unmount();

    const productionFetch = stubPage({
      bookings: [booking("awaiting_payment")],
      paymentResult: response(payment()),
    });
    renderPage();
    await screen.findByText("Menunggu pembayaran");
    expect(
      screen.queryByRole("button", {
        name: "Simulasikan pembayaran berhasil",
      }),
    ).not.toBeInTheDocument();
    expect(
      productionFetch.mock.calls.some(([url]) => String(url).includes("/dev/")),
    ).toBe(false);
  });

  it("hides creator release controls in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const fetchMock = stubPage({
      me: CREATOR,
      bookings: [],
      incoming: [booking("completed")],
      paymentResult: response(payment("held")),
    });
    renderPage();
    await screen.findByText("Dana tercatat aman");
    expect(
      screen.queryByRole("button", { name: "Simulasikan pencairan" }),
    ).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes("/dev/")),
    ).toBe(false);
  });

  it("shows the client booking summary without creator settlement details", async () => {
    stubPage({
      bookings: [booking("awaiting_payment")],
      paymentResult: response(payment()),
    });
    renderPage();
    expect(await screen.findByText("Studio Cahaya")).toBeVisible();
    expect(screen.getByText("1 September 2026")).toBeVisible();
    expect(screen.getAllByText("Bandung")).toHaveLength(2);
    expect(screen.getByText(/Rp\s*1\.500\.000/)).toBeVisible();
    expect(screen.queryByText("Biaya platform")).not.toBeInTheDocument();
    expect(screen.queryByText("Pendapatan kreator")).not.toBeInTheDocument();
  });

  it("shows fee and creator net only for the incoming creator booking", async () => {
    stubPage({
      me: CREATOR,
      bookings: [],
      incoming: [booking("completed")],
      paymentResult: response(payment("held")),
    });
    renderPage();
    expect(await screen.findByText("Biaya platform")).toBeVisible();
    expect(screen.getByText(/Rp\s*150\.000/)).toBeVisible();
    expect(screen.getByText("Pendapatan kreator")).toBeVisible();
    expect(screen.getByText(/Rp\s*1\.350\.000/)).toBeVisible();
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

  it("keeps creation revalidation authoritative before enabling the next action", async () => {
    let resolvePaymentRefresh!: (value: MockResponse) => void;
    let resolveBookingsRefresh!: (value: MockResponse) => void;
    let resolveIncomingRefresh!: (value: MockResponse) => void;
    const paymentRefresh = new Promise<MockResponse>((resolve) => {
      resolvePaymentRefresh = resolve;
    });
    const bookingsRefresh = new Promise<MockResponse>((resolve) => {
      resolveBookingsRefresh = resolve;
    });
    const incomingRefresh = new Promise<MockResponse>((resolve) => {
      resolveIncomingRefresh = resolve;
    });
    let paymentGets = 0;
    let bookingGets = 0;
    let incomingGets = 0;
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/me")) return Promise.resolve(response(CLIENT));
      if (url.endsWith("/bookings/incoming")) {
        incomingGets += 1;
        return incomingGets === 1
          ? Promise.resolve(response([]))
          : incomingRefresh;
      }
      if (url.endsWith("/bookings")) {
        bookingGets += 1;
        return bookingGets === 1
          ? Promise.resolve(response([booking()]))
          : bookingsRefresh;
      }
      if (url.endsWith("/bookings/b1/payments") && init?.method === "POST")
        return Promise.resolve(response(payment()));
      paymentGets += 1;
      return paymentGets === 1
        ? Promise.resolve(response(null, 404))
        : paymentRefresh;
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    await userEvent.click(
      await screen.findByRole("button", { name: "Buat pembayaran" }),
    );
    await waitFor(() => {
      expect(paymentGets).toBe(2);
      expect(bookingGets).toBe(2);
      expect(incomingGets).toBe(2);
    });
    expect(screen.getByText("Menunggu pembayaran")).toBeVisible();
    expect(
      screen.queryByRole("button", {
        name: "Simulasikan pembayaran berhasil",
      }),
    ).not.toBeInTheDocument();

    resolvePaymentRefresh(response(payment()));
    resolveBookingsRefresh(response([booking("awaiting_payment")]));
    resolveIncomingRefresh(response([]));
    expect(
      await screen.findByRole("button", {
        name: "Simulasikan pembayaran berhasil",
      }),
    ).toBeEnabled();
  });

  it("refetches payment and booking lists after simulate-paid", async () => {
    let resolvePaymentRefresh!: (value: MockResponse) => void;
    let resolveBookingsRefresh!: (value: MockResponse) => void;
    let resolveIncomingRefresh!: (value: MockResponse) => void;
    const paymentRefresh = new Promise<MockResponse>((resolve) => {
      resolvePaymentRefresh = resolve;
    });
    const bookingsRefresh = new Promise<MockResponse>((resolve) => {
      resolveBookingsRefresh = resolve;
    });
    const incomingRefresh = new Promise<MockResponse>((resolve) => {
      resolveIncomingRefresh = resolve;
    });
    let paymentGets = 0;
    let bookingGets = 0;
    let incomingGets = 0;
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/me")) return Promise.resolve(response(CLIENT));
      if (url.endsWith("/bookings/incoming")) {
        incomingGets += 1;
        return incomingGets === 1
          ? Promise.resolve(response([]))
          : incomingRefresh;
      }
      if (url.endsWith("/bookings")) {
        bookingGets += 1;
        return bookingGets === 1
          ? Promise.resolve(response([booking("awaiting_payment")]))
          : bookingsRefresh;
      }
      if (
        url.endsWith("/dev/payments/p1/simulate-paid") &&
        init?.method === "POST"
      )
        return Promise.resolve(response(payment("held")));
      paymentGets += 1;
      return paymentGets === 1
        ? Promise.resolve(response(payment()))
        : paymentRefresh;
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Simulasikan pembayaran berhasil",
      }),
    );
    expect(await screen.findByText("Dana tercatat aman")).toBeVisible();
    await waitFor(() => {
      expect(paymentGets).toBe(2);
      expect(bookingGets).toBe(2);
      expect(incomingGets).toBe(2);
    });
    expect(
      screen.queryByRole("button", {
        name: "Simulasikan pembayaran berhasil",
      }),
    ).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith("/dev/payments/p1/simulate-paid"),
      ),
    ).toHaveLength(1);
    resolvePaymentRefresh(response(payment("held")));
    resolveBookingsRefresh(response([booking("confirmed")]));
    resolveIncomingRefresh(response([]));
    expect(await screen.findByText("Dana tercatat aman")).toBeVisible();
  });

  it("refetches payment and booking lists after simulate-release", async () => {
    let resolvePaymentRefresh!: (value: MockResponse) => void;
    let resolveBookingsRefresh!: (value: MockResponse) => void;
    let resolveIncomingRefresh!: (value: MockResponse) => void;
    const paymentRefresh = new Promise<MockResponse>((resolve) => {
      resolvePaymentRefresh = resolve;
    });
    const bookingsRefresh = new Promise<MockResponse>((resolve) => {
      resolveBookingsRefresh = resolve;
    });
    const incomingRefresh = new Promise<MockResponse>((resolve) => {
      resolveIncomingRefresh = resolve;
    });
    let paymentGets = 0;
    let bookingGets = 0;
    let incomingGets = 0;
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/me")) return Promise.resolve(response(CREATOR));
      if (url.endsWith("/bookings/incoming")) {
        incomingGets += 1;
        return incomingGets === 1
          ? Promise.resolve(response([booking("completed")]))
          : incomingRefresh;
      }
      if (url.endsWith("/bookings")) {
        bookingGets += 1;
        return bookingGets === 1
          ? Promise.resolve(response([]))
          : bookingsRefresh;
      }
      if (
        url.endsWith("/dev/payments/p1/simulate-release") &&
        init?.method === "POST"
      )
        return Promise.resolve(response(payment("released")));
      paymentGets += 1;
      return paymentGets === 1
        ? Promise.resolve(response(payment("held")))
        : paymentRefresh;
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await userEvent.click(
      await screen.findByRole("button", { name: "Simulasikan pencairan" }),
    );
    expect(await screen.findByText("Pembayaran telah dilepas")).toBeVisible();
    await waitFor(() => {
      expect(paymentGets).toBe(2);
      expect(bookingGets).toBe(2);
      expect(incomingGets).toBe(2);
    });
    expect(
      screen.queryByRole("button", { name: "Simulasikan pencairan" }),
    ).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith("/dev/payments/p1/simulate-release"),
      ),
    ).toHaveLength(1);
    resolvePaymentRefresh(response(payment("released")));
    resolveBookingsRefresh(response([]));
    resolveIncomingRefresh(response([booking("completed")]));
    expect(await screen.findByText("Pembayaran telah dilepas")).toBeVisible();
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
    const fetchMock = stubPage({ bookings: [{ ...booking(), id: "other" }] });
    renderPage();
    expect(await screen.findByText("Booking tidak ditemukan.")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Buat pembayaran" }),
    ).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).endsWith("/bookings/b1/payments"),
      ),
    ).toBe(false);
  });

  it("waits for an incoming match after my bookings resolve empty", async () => {
    let resolveIncoming!: (value: MockResponse) => void;
    const incomingResult = new Promise<MockResponse>((resolve) => {
      resolveIncoming = resolve;
    });
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/auth/me")) return Promise.resolve(response(CREATOR));
      if (url.endsWith("/bookings/incoming")) return incomingResult;
      if (url.endsWith("/bookings")) return Promise.resolve(response([]));
      return Promise.resolve(response(payment("held")));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).endsWith("/bookings")),
      ).toBe(true),
    );
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).endsWith("/bookings/b1/payments"),
      ),
    ).toBe(false);
    resolveIncoming(response([booking("completed")]));
    expect(await screen.findByText("Dana tercatat aman")).toBeVisible();
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).endsWith("/bookings/b1/payments"),
      ),
    ).toBe(true);
  });
});
