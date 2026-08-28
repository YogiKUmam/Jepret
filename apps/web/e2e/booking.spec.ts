import { expect, test } from "@playwright/test";

import type { BookingStatus } from "@/lib/api";

const CLIENT = { email: "klien@jepret.local", password: "klien12345" };
const CREATOR = { email: "kreator@jepret.local", password: "kreator12345" };

interface IncomingBooking {
  id: string;
  event_date: string;
  notes: string;
  status: BookingStatus;
}

interface IncomingBookingEnvelope {
  data: IncomingBooking[];
}

interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
  };
}

test.describe.configure({ mode: "serial" });

const BLOCKING_BOOKING_STATUSES: ReadonlySet<BookingStatus> = new Set([
  "accepted",
  "awaiting_payment",
  "confirmed",
  "in_progress",
  "delivered",
]);
const EVENT_DATE_CANDIDATE_COUNT = 730;
const MAX_BOOKING_ATTEMPTS = 5;

function isoDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

function addUtcDays(date: Date, days: number) {
  const result = new Date(date);
  result.setUTCDate(result.getUTCDate() + days);
  return result;
}

async function login(
  page: import("@playwright/test").Page,
  account: { email: string; password: string },
) {
  await page.goto("/masuk");
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Masuk" }).click();
  await expect(page).toHaveURL(/\/profil$/);
}

async function logout(page: import("@playwright/test").Page) {
  await page.goto("/profil");
  await page.getByRole("button", { name: "Keluar" }).click();
  await expect(page).toHaveURL(/\/masuk$/);
}

function bookingCard(
  page: import("@playwright/test").Page,
  bookingNote: string,
  status: string,
) {
  return page
    .getByRole("listitem")
    .filter({ hasText: bookingNote })
    .filter({ hasText: status });
}

async function findAvailableEventDate(
  page: import("@playwright/test").Page,
  triedDates: ReadonlySet<string>,
  forcedCandidate?: string,
) {
  await login(page, CREATOR);
  const response = await page.request.get("/api/v1/bookings/incoming");
  expect(response.ok()).toBeTruthy();

  const envelope = (await response.json()) as IncomingBookingEnvelope;
  const activeDates = new Set(
    envelope.data
      .filter((booking) => BLOCKING_BOOKING_STATUSES.has(booking.status))
      .map((booking) => booking.event_date),
  );
  const now = new Date();
  const start = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()),
  );
  start.setUTCFullYear(start.getUTCFullYear() + 1);

  if (forcedCandidate && !triedDates.has(forcedCandidate)) {
    await logout(page);
    return forcedCandidate;
  }

  const randomSeed = Number.parseInt(crypto.randomUUID().slice(0, 8), 16);
  const startIndex = randomSeed % EVENT_DATE_CANDIDATE_COUNT;

  for (let step = 0; step < EVENT_DATE_CANDIDATE_COUNT; step += 1) {
    const candidateIndex = (startIndex + step) % EVENT_DATE_CANDIDATE_COUNT;
    const candidate = isoDate(addUtcDays(start, candidateIndex));
    if (!activeDates.has(candidate) && !triedDates.has(candidate)) {
      await logout(page);
      return candidate;
    }
  }

  await logout(page);
  throw new Error(
    `Setup E2E gagal: tidak ada tanggal acara yang tersedia dalam ${EVENT_DATE_CANDIDATE_COUNT} hari.`,
  );
}

function isBookingActionResponse(
  response: import("@playwright/test").Response,
  bookingId: string,
  action: "accept" | "reject",
) {
  return (
    response.request().method() === "POST" &&
    new URL(response.url()).pathname ===
      `/api/v1/bookings/${bookingId}/${action}`
  );
}

async function requestBooking(
  page: import("@playwright/test").Page,
  eventDate: string,
  bookingNote: string,
) {
  await login(page, CLIENT);
  await page.goto("/");
  await page
    .getByRole("searchbox", { name: "Cari kreator" })
    .fill("Studio Cahaya");
  await page.getByRole("button", { name: "Terapkan" }).click();
  await page.getByRole("link", { name: /studio cahaya/i }).click();
  await page.getByRole("link", { name: /ajukan booking/i }).click();

  await page.getByLabel("Tanggal acara").fill(eventDate);
  await page.getByLabel("Kota acara").fill("Bandung");
  await page.getByLabel("Catatan (opsional)").fill(bookingNote);
  await page.getByRole("button", { name: "Kirim permintaan" }).click();

  await expect(page).toHaveURL(/\/booking$/);
  const card = bookingCard(page, bookingNote, "Menunggu konfirmasi");
  await expect(card).toContainText("Menunggu konfirmasi");
}

async function requestAndAcceptBooking(
  page: import("@playwright/test").Page,
  notePrefix: string,
  forcedFirstCandidate?: string,
) {
  const triedDates = new Set<string>();

  for (let attempt = 1; attempt <= MAX_BOOKING_ATTEMPTS; attempt += 1) {
    const eventDate = await findAvailableEventDate(
      page,
      triedDates,
      attempt === 1 ? forcedFirstCandidate : undefined,
    );
    const bookingNote = `${notePrefix} attempt ${attempt}`;
    await requestBooking(page, eventDate, bookingNote);
    await logout(page);
    await login(page, CREATOR);
    await page.goto("/booking/masuk");

    const incomingResponse = await page.request.get(
      "/api/v1/bookings/incoming",
    );
    expect(incomingResponse.ok()).toBeTruthy();
    const incomingEnvelope =
      (await incomingResponse.json()) as IncomingBookingEnvelope;
    const booking = incomingEnvelope.data.find(
      (item) => item.notes === bookingNote,
    );
    if (!booking) {
      throw new Error(
        `Setup E2E gagal: booking attempt ${attempt} tidak ditemukan.`,
      );
    }

    const requestedCard = bookingCard(page, bookingNote, "Menunggu konfirmasi");
    await expect(requestedCard).toContainText("Klien Demo");
    const acceptResponsePromise = page.waitForResponse((response) =>
      isBookingActionResponse(response, booking.id, "accept"),
    );
    await requestedCard.getByRole("button", { name: "Terima" }).click();
    const acceptResponse = await acceptResponsePromise;

    if (acceptResponse.ok()) {
      await expect(bookingCard(page, bookingNote, "Diterima")).toBeVisible();
      return { attempt, bookingNote, eventDate };
    }

    const errorEnvelope = (await acceptResponse.json()) as ApiErrorEnvelope;
    if (errorEnvelope.error.code !== "DATE_UNAVAILABLE") {
      throw new Error(
        `Accept booking gagal: ${errorEnvelope.error.code} - ${errorEnvelope.error.message}`,
      );
    }

    await expect(requestedCard).toContainText("Menunggu konfirmasi");
    const rejectResponsePromise = page.waitForResponse((response) =>
      isBookingActionResponse(response, booking.id, "reject"),
    );
    await requestedCard.getByRole("button", { name: "Tolak" }).click();
    const rejectResponse = await rejectResponsePromise;
    expect(rejectResponse.ok()).toBeTruthy();
    await expect(bookingCard(page, bookingNote, "Ditolak")).toBeVisible();

    triedDates.add(eventDate);
    await logout(page);
  }

  throw new Error(
    `Setup E2E gagal: booking belum dapat diterima setelah ${MAX_BOOKING_ATTEMPTS} percobaan.`,
  );
}

async function cancelAcceptedBooking(
  page: import("@playwright/test").Page,
  bookingNote: string,
) {
  await page.goto("/booking");
  const card = bookingCard(page, bookingNote, "Diterima");
  await card.getByRole("button", { name: "Batalkan" }).click();
  await expect(bookingCard(page, bookingNote, "Dibatalkan")).toBeVisible();
}

async function payBooking(
  page: import("@playwright/test").Page,
  bookingNote: string,
) {
  await logout(page);
  await login(page, CLIENT);
  await page.goto("/booking");
  const card = bookingCard(page, bookingNote, "Diterima");
  await card.getByRole("link", { name: "Bayar sekarang" }).click();
  await page.getByRole("button", { name: "Buat pembayaran" }).click();
  await page
    .getByRole("button", { name: "Simulasikan pembayaran berhasil" })
    .click();
  await expect(page.getByText("Dana tercatat aman")).toBeVisible();
  return page.url();
}

test("recovers when the first booking date becomes unavailable", async ({
  page,
}) => {
  const blocker = await requestAndAcceptBooking(
    page,
    `E2E blocker ${crypto.randomUUID()}`,
  );

  await logout(page);
  const notePrefix = `E2E collision ${crypto.randomUUID()}`;
  const recovered = await requestAndAcceptBooking(
    page,
    notePrefix,
    blocker.eventDate,
  );
  expect(recovered.attempt).toBe(2);
  expect(recovered.eventDate).not.toBe(blocker.eventDate);
  await expect(
    bookingCard(page, `${notePrefix} attempt 1`, "Ditolak"),
  ).toBeVisible();

  await logout(page);
  await login(page, CLIENT);
  await cancelAcceptedBooking(page, blocker.bookingNote);
  await cancelAcceptedBooking(page, recovered.bookingNote);
});

test("client pays an accepted booking and opens the workspace", async ({
  page,
}) => {
  const { bookingNote } = await requestAndAcceptBooking(
    page,
    `E2E confirmed ${crypto.randomUUID()}`,
  );
  await payBooking(page, bookingNote);

  await page.goto("/booking");
  const confirmedCard = bookingCard(page, bookingNote, "Terkonfirmasi");
  await confirmedCard.getByRole("link", { name: "Buka ruang kerja" }).click();
  await expect(page).toHaveURL(/\/booking\/[^/]+$/);
  await expect(page.getByText("Terkonfirmasi")).toBeVisible();
});

test("cancelling a paid booking refunds the payment", async ({ page }) => {
  const { bookingNote } = await requestAndAcceptBooking(
    page,
    `E2E refund ${crypto.randomUUID()}`,
  );
  const paymentUrl = await payBooking(page, bookingNote);

  await page.goto("/booking");
  const card = bookingCard(page, bookingNote, "Terkonfirmasi");
  await card.getByRole("button", { name: "Batalkan" }).click();
  await expect(bookingCard(page, bookingNote, "Dibatalkan")).toBeVisible();

  await page.goto(paymentUrl);
  await expect(page.getByText("Pembayaran dikembalikan")).toBeVisible();
});
