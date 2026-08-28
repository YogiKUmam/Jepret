import { expect, test, type Browser } from "@playwright/test";

import type { BookingStatus } from "@/lib/api";

const CLIENT = { email: "klien@jepret.local", password: "klien12345" };
const CREATOR = { email: "kreator@jepret.local", password: "kreator12345" };
const OUTSIDER = { email: "admin@jepret.local", password: "admin12345" };

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
) {
  await login(page, CREATOR);
  const response = await page.request.get("/api/v1/bookings/incoming");
  expect(response.ok()).toBeTruthy();

  const envelope = (await response.json()) as {
    data: Array<{ event_date: string; status: BookingStatus }>;
  };
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

test.describe.configure({ mode: "serial" });

test("completes the entire booking workspace lifecycle: chat, deliver, accept, release payment", async ({
  browser,
}) => {
  const clientContext = await browser.newContext();
  const creatorContext = await browser.newContext();
  const outsiderContext = await browser.newContext();

  const clientPage = await clientContext.newPage();
  const creatorPage = await creatorContext.newPage();
  const outsiderPage = await outsiderContext.newPage();

  const triedDates = new Set<string>();
  const eventDate = await findAvailableEventDate(clientPage, triedDates);
  const bookingNote = `E2E workspace test ${crypto.randomUUID()}`;

  // 1. Client creates a booking request
  await login(clientPage, CLIENT);
  await clientPage.goto("/");
  await clientPage
    .getByRole("searchbox", { name: "Cari kreator" })
    .fill("Studio Cahaya");
  await clientPage.getByRole("button", { name: "Terapkan" }).click();
  await clientPage.getByRole("link", { name: /studio cahaya/i }).click();
  await clientPage.getByRole("link", { name: /ajukan booking/i }).click();

  await clientPage.getByLabel("Tanggal acara").fill(eventDate);
  await clientPage.getByLabel("Kota acara").fill("Bandung");
  await clientPage.getByLabel("Catatan (opsional)").fill(bookingNote);
  await clientPage.getByRole("button", { name: "Kirim permintaan" }).click();

  await expect(clientPage).toHaveURL(/\/booking$/);
  const clientCard = bookingCard(
    clientPage,
    bookingNote,
    "Menunggu konfirmasi",
  );
  await expect(clientCard).toBeVisible();

  // 2. Creator accepts the booking
  await login(creatorPage, CREATOR);
  await creatorPage.goto("/booking/masuk");
  const creatorCard = bookingCard(
    creatorPage,
    bookingNote,
    "Menunggu konfirmasi",
  );
  await expect(creatorCard).toBeVisible();
  await creatorCard.getByRole("button", { name: "Terima" }).click();
  await expect(bookingCard(creatorPage, bookingNote, "Diterima")).toBeVisible();

  // 3. Client pays the accepted booking
  await clientPage.goto("/booking");
  const acceptedCard = bookingCard(clientPage, bookingNote, "Diterima");
  await acceptedCard.getByRole("link", { name: "Bayar sekarang" }).click();
  await clientPage.getByRole("button", { name: "Buat pembayaran" }).click();
  await clientPage
    .getByRole("button", { name: "Simulasikan pembayaran berhasil" })
    .click();
  await expect(clientPage.getByText("Dana tercatat aman")).toBeVisible();

  // 4. Client navigates to workspace
  await clientPage.goto("/booking");
  const confirmedCard = bookingCard(clientPage, bookingNote, "Terkonfirmasi");
  await confirmedCard.getByRole("link", { name: "Buka ruang kerja" }).click();
  await expect(clientPage).toHaveURL(/\/booking\/[^/]+$/);

  const workspaceUrl = clientPage.url();
  await expect(clientPage.getByText("Terkonfirmasi").first()).toBeVisible();

  // 5. Client sends chat message
  const chatMessage = `Mohon foto keluarga juga (${crypto.randomUUID().slice(0, 6)}).`;
  await clientPage.getByPlaceholder(/Tulis pesan…/i).fill(chatMessage);
  await clientPage.getByRole("button", { name: "Kirim pesan" }).click();
  await expect(clientPage.getByText(chatMessage)).toBeVisible();

  // 6. Creator enters workspace and sees the message
  await creatorPage.goto("/booking/masuk");
  const creatorConfirmed = bookingCard(
    creatorPage,
    bookingNote,
    "Terkonfirmasi",
  );
  await creatorConfirmed
    .getByRole("link", { name: "Buka ruang kerja" })
    .click();
  await expect(creatorPage).toHaveURL(workspaceUrl);
  await expect(creatorPage.getByText(chatMessage)).toBeVisible();

  // 7. Creator starts session
  await creatorPage.getByRole("button", { name: "Mulai sesi" }).click();
  await expect(creatorPage.getByText("Sesi Berlangsung").first()).toBeVisible();

  // 8. Creator uploads a deliverable file & adds external link
  await creatorPage.getByRole("tab", { name: "Hasil" }).click();
  await expect(
    creatorPage.getByRole("tabpanel", { name: "Hasil" }),
  ).toBeVisible();

  // Add external link deliverable
  await creatorPage
    .getByRole("button", { name: /Tautan Google Drive/i })
    .click();
  await creatorPage.getByLabel("Judul Tautan").fill("Album Google Drive");
  await creatorPage
    .getByLabel("URL Tautan Cloud Drive")
    .fill("https://drive.google.com/drive/folders/test123xyz");
  await creatorPage
    .getByRole("button", { name: "Simpan Tautan Hasil" })
    .click();

  await expect(creatorPage.getByText("Album Google Drive")).toBeVisible();
  await expect(creatorPage.getByText("drive.google.com")).toBeVisible();

  // 9. Creator delivers results
  await creatorPage.getByRole("button", { name: "Kirim hasil" }).click();
  await expect(creatorPage.getByText("Hasil Dikirim").first()).toBeVisible();

  // 10. Client verifies deliverables and accepts
  await clientPage.reload();
  await clientPage.getByRole("tab", { name: "Hasil" }).click();
  await expect(clientPage.getByText("Album Google Drive")).toBeVisible();

  await clientPage.getByRole("button", { name: "Terima hasil" }).click();
  const dialog = clientPage.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Ya, terima hasil" }).click();

  // 11. Completion and payment release verified
  await expect(clientPage.getByText("Selesai").first()).toBeVisible();
  await clientPage.getByRole("link", { name: "Lihat pembayaran" }).click();
  await expect(clientPage.getByText("Pembayaran telah dilepas")).toBeVisible();

  // 12. Outsider access check
  await login(outsiderPage, OUTSIDER);
  await outsiderPage.goto(workspaceUrl);
  await expect(
    outsiderPage.getByText("Ruang Kerja Tidak Ditemukan"),
  ).toBeVisible();

  await clientContext.close();
  await creatorContext.close();
  await outsiderContext.close();
});
