import { expect, test } from "@playwright/test";

const CLIENT = { email: "klien@jepret.local", password: "klien12345" };
const CREATOR = { email: "kreator@jepret.local", password: "kreator12345" };

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
    .locator("li", { hasText: bookingNote })
    .filter({ hasText: status });
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

async function acceptBooking(
  page: import("@playwright/test").Page,
  bookingNote: string,
) {
  await logout(page);
  await login(page, CREATOR);
  await page.goto("/booking/masuk");
  const incoming = bookingCard(page, bookingNote, "Menunggu konfirmasi");
  await expect(incoming).toContainText("Klien Demo");
  await incoming.getByRole("button", { name: "Terima" }).click();
  await expect(bookingCard(page, bookingNote, "Diterima")).toBeVisible();
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

test("client pays an accepted booking and the creator releases it", async ({
  page,
}) => {
  const eventDate = "2027-03-15";
  const bookingNote = `E2E release ${Date.now()}`;

  await requestBooking(page, eventDate, bookingNote);
  await acceptBooking(page, bookingNote);
  const paymentUrl = await payBooking(page, bookingNote);

  await logout(page);
  await login(page, CREATOR);
  await page.goto("/booking/masuk");
  const incoming = bookingCard(page, bookingNote, "Terkonfirmasi");
  await incoming.getByRole("button", { name: "Tandai selesai" }).click();
  await expect(bookingCard(page, bookingNote, "Selesai")).toBeVisible();

  await page.goto(paymentUrl);
  await page.getByRole("button", { name: "Simulasikan pencairan" }).click();
  await expect(page.getByText("Pembayaran telah dilepas")).toBeVisible();
});

test("cancelling a paid booking refunds the payment", async ({ page }) => {
  const eventDate = "2027-03-16";
  const bookingNote = `E2E refund ${Date.now()}`;

  await requestBooking(page, eventDate, bookingNote);
  await acceptBooking(page, bookingNote);
  const paymentUrl = await payBooking(page, bookingNote);

  await page.goto("/booking");
  const card = bookingCard(page, bookingNote, "Terkonfirmasi");
  await card.getByRole("button", { name: "Batalkan" }).click();
  await expect(bookingCard(page, bookingNote, "Dibatalkan")).toBeVisible();

  await page.goto(paymentUrl);
  await expect(page.getByText("Pembayaran dikembalikan")).toBeVisible();
});
