import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { QueryProvider } from "@/lib/query-provider";

import HomePage from "./page";

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: () => Promise.resolve(body) };
}

function creator(id: string, name: string) {
  return {
    id,
    display_name: name,
    city: "Bandung",
    bio: "",
    specialty: "wedding",
    starting_price_idr: 1_500_000,
  };
}

function renderHome() {
  return render(
    <QueryProvider>
      <HomePage />
    </QueryProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HomePage", () => {
  it("renders discovery shell and live creator listing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          data: {
            items: [creator("a", "Studio Cahaya")],
            next_cursor: null,
          },
        }),
      ),
    );
    renderHome();
    expect(
      screen.getByRole("heading", { name: /cerita yang layak diingat/i }),
    ).toBeVisible();
    expect(
      screen.getByRole("searchbox", { name: /cari kreator/i }),
    ).toHaveClass("min-h-11");
    expect(
      screen.getByRole("navigation", { name: /navigasi utama/i }),
    ).toBeVisible();
    expect(await screen.findByText("Studio Cahaya")).toBeVisible();
    expect(screen.getByRole("link", { name: /studio cahaya/i })).toHaveAttribute(
      "href",
      "/kreator/a",
    );
    expect(
      screen.queryByRole("button", { name: /muat lebih/i }),
    ).not.toBeInTheDocument();
  });

  it("loads the next page via Muat lebih", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          data: { items: [creator("a", "Studio Cahaya")], next_cursor: "c1" },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          data: { items: [creator("b", "Rana Potret")], next_cursor: null },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    renderHome();
    await userEvent.click(
      await screen.findByRole("button", { name: /muat lebih/i }),
    );
    expect(await screen.findByText("Rana Potret")).toBeVisible();
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/creators?cursor=c1",
      expect.anything(),
    );
  });

  it("shows an empty state after a filter without matches", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ data: { items: [], next_cursor: null } }),
      ),
    );
    renderHome();
    expect(
      await screen.findByText("Tidak ada kreator yang cocok."),
    ).toBeVisible();
  });
});
