import { expect, test } from "@playwright/test";

test("marketplace search leads to a creator detail page", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Pilihan di dekatmu" }),
  ).toBeVisible();
  await expect(
    page.getByRole("searchbox", { name: "Cari kreator" }),
  ).toBeVisible();

  await page
    .getByRole("searchbox", { name: "Cari kreator" })
    .fill("Studio Cahaya");
  await page.getByRole("button", { name: "Terapkan" }).click();

  const card = page.getByRole("link", { name: /studio cahaya/i }).first();
  await expect(card).toBeVisible();
  await card.click();

  await expect(page).toHaveURL(/\/kreator\/[^/]+$/);
  await expect(
    page.getByRole("heading", { name: "Studio Cahaya", level: 1 }),
  ).toBeVisible();
  await expect(page.getByText(/bandung · wedding/i)).toBeVisible();
  await expect(
    page.getByRole("link", { name: /ajukan booking/i }),
  ).toBeVisible();
});

test("filter without matches shows the empty state", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Kota").fill("Atlantis");
  await page.getByRole("button", { name: "Terapkan" }).click();
  await expect(page.getByText("Tidak ada kreator yang cocok.")).toBeVisible();
});
