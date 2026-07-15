import { expect, test } from "@playwright/test";

test("mobile shell and API share one origin", async ({ page, request }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /cerita yang layak diingat/i }),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: /navigasi utama/i }),
  ).toBeVisible();

  const health = await request.get("/health", {
    headers: { "X-Request-ID": "e2e-request-123" },
  });
  expect(health.ok()).toBeTruthy();
  await expect(health.json()).resolves.toEqual({ data: { status: "ok" } });
  expect(health.headers()["x-request-id"]).toBe("e2e-request-123");
});

test("gateway forwards WebSocket upgrades", async ({ page }) => {
  await page.goto("/");
  const result = await page.evaluate(
    () =>
      new Promise((resolve, reject) => {
        const protocol = location.protocol === "https:" ? "wss" : "ws";
        const socket = new WebSocket(
          `${protocol}://${location.host}/ws/health`,
        );
        socket.onmessage = (event) => resolve(JSON.parse(event.data));
        socket.onerror = () => reject(new Error("WebSocket probe failed"));
      }),
  );
  expect(result).toEqual({ status: "ok" });
});
