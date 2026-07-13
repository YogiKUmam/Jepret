import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    trace: "on-first-retry",
  },
  projects: [{ name: "mobile-chromium", use: { ...devices["Pixel 7"] } }],
  retries: process.env.CI ? 2 : 0,
});
