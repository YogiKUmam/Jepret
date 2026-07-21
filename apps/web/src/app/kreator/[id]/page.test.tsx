import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { QueryProvider } from "@/lib/query-provider";

import KreatorDetailPage from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "abc" }),
}));

function renderPage() {
  return render(
    <QueryProvider>
      <KreatorDetailPage />
    </QueryProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("KreatorDetailPage", () => {
  it("renders the creator profile", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            data: {
              id: "abc",
              display_name: "Studio Cahaya",
              city: "Bandung",
              bio: "Fotografer pernikahan.",
              specialty: "wedding",
              starting_price_idr: 1_500_000,
            },
          }),
      }),
    );
    renderPage();
    expect(
      await screen.findByRole("heading", { name: "Studio Cahaya" }),
    ).toBeVisible();
    expect(screen.getByText(/bandung · wedding/i)).toBeVisible();
    expect(screen.getByText("Fotografer pernikahan.")).toBeVisible();
    expect(screen.getByText(/mulai rp/i)).toBeVisible();
    expect(
      screen.getByRole("button", { name: /hubungi kreator/i }),
    ).toBeDisabled();
  });

  it("shows a not-found state for missing creators", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: () =>
          Promise.resolve({
            error: { code: "NOT_FOUND", message: "Kreator tidak ditemukan." },
          }),
      }),
    );
    renderPage();
    expect(
      await screen.findByRole("heading", { name: /kreator tidak ditemukan/i }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: /kembali ke beranda/i }),
    ).toHaveAttribute("href", "/");
  });
});
