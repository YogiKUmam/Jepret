import { expect, test } from "@playwright/test";

test("register, logout, login, and submit a creator draft", async ({
  page,
}) => {
  const email = `e2e-${Date.now()}@jepret.local`;
  const password = "sandi-aman-123";

  // Register (auto-login) and land on the profile page.
  await page.goto("/daftar");
  await page.getByLabel("Nama lengkap").fill("Pengguna E2E");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Daftar" }).click();
  await expect(page).toHaveURL(/\/profil$/);
  await expect(page.getByText(email)).toBeVisible();

  // Logout returns to the login page.
  await page.getByRole("button", { name: "Keluar" }).click();
  await expect(page).toHaveURL(/\/masuk$/);

  // Login again.
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Masuk" }).click();
  await expect(page).toHaveURL(/\/profil$/);

  // Create a creator draft and submit it for verification.
  await page.getByRole("link", { name: "Jadi kreator" }).click();
  await expect(page).toHaveURL(/\/profil\/kreator$/);
  await page.getByLabel("Nama studio / kreator").fill("Studio E2E");
  await page.getByLabel("Kota").fill("Bandung");
  await page.getByLabel(/Spesialisasi/).fill("wedding");
  await page.getByLabel(/Harga mulai/).fill("1500000");
  await page.getByRole("button", { name: "Simpan draft" }).click();
  await expect(page.getByText("Draft tersimpan.")).toBeVisible();

  await page.getByRole("button", { name: "Ajukan verifikasi" }).click();
  await expect(page.getByText(/menunggu verifikasi/i)).toBeVisible();
});

test("login page rejects wrong credentials with a friendly message", async ({
  page,
}) => {
  await page.goto("/masuk");
  await page.getByLabel("Email").fill("tidak-ada@jepret.local");
  await page.getByLabel("Password").fill("password-salah");
  await page.getByRole("button", { name: "Masuk" }).click();
  await expect(page.getByText("Email atau password salah.")).toBeVisible();
});
