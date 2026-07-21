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

test("client requests a booking and the creator accepts it", async ({
  page,
}) => {
  const eventDate = "2027-03-15";

  await login(page, CLIENT);
  await page.goto("/");
  await page.getByRole("searchbox", { name: "Cari kreator" }).fill("Studio Cahaya");
  await page.getByRole("button", { name: "Terapkan" }).click();
  await page.getByRole("link", { name: /studio cahaya/i }).click();
  await page.getByRole("link", { name: /ajukan booking/i }).click();

  await page.getByLabel("Tanggal acara").fill(eventDate);
  await page.getByLabel("Kota acara").fill("Bandung");
  await page.getByRole("button", { name: "Kirim permintaan" }).click();

  await expect(page).toHaveURL(/\/booking$/);
  const card = page.locator("li", { hasText: eventDate });
  await expect(card).toContainText("Menunggu konfirmasi");

  await page.goto("/profil");
  await page.getByRole("button", { name: "Keluar" }).click();

  await login(page, CREATOR);
  await page.goto("/booking/masuk");
  const incoming = page.locator("li", { hasText: eventDate });
  await expect(incoming).toContainText("Klien Demo");
  await incoming.getByRole("button", { name: "Terima" }).click();
  await expect(incoming).toContainText("Diterima");
});
