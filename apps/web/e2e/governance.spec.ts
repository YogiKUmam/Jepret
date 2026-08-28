import { expect, test } from "@playwright/test";

const ADMIN = { email: "admin@jepret.local", password: "admin12345" };
const CLIENT = { email: "klien@jepret.local", password: "klien12345" };

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

test.describe("Phase 7 Governance, Reviews & Disputes", () => {
  test("admin dashboard is accessible by admin and shows metrics and management tabs", async ({
    page,
  }) => {
    await login(page, ADMIN);
    await page.goto("/admin");

    await expect(
      page.getByRole("heading", { name: /ringkasan operasional/i }),
    ).toBeVisible();

    await expect(
      page.getByText(/total gross merchandise value/i),
    ).toBeVisible();
    await expect(page.getByText(/verifikasi kreator/i)).toBeVisible();
    await expect(page.getByText(/sengketa aktif/i)).toBeVisible();

    // Navigate to creator verification tab
    await page.goto("/admin/kreator");
    await expect(
      page.getByRole("heading", { name: /verifikasi profil kreator/i }),
    ).toBeVisible();

    // Navigate to disputes mediation tab
    await page.goto("/admin/sengketa");
    await expect(
      page.getByRole("heading", { name: /manajemen sengketa & mediasi/i }),
    ).toBeVisible();
  });

  test("non-admin user is redirected away from /admin", async ({ page }) => {
    await login(page, CLIENT);
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/masuk$/);
  });
});
