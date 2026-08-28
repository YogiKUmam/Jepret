import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminOverviewPage from "./page";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AdminOverviewPage", () => {
  it("renders metrics from overview API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            data: {
              total_users: 120,
              total_creators: 35,
              pending_creator_applications: 4,
              total_bookings: 88,
              active_disputes: 2,
              total_gmv_idr: 45_000_000,
            },
          }),
      }),
    );

    render(<AdminOverviewPage />);

    expect(
      await screen.findByRole("heading", { name: /ringkasan operasional/i }),
    ).toBeVisible();

    expect(screen.getByText("4")).toBeVisible();
    expect(screen.getByText("2")).toBeVisible();
    expect(screen.getByText("88")).toBeVisible();
    expect(screen.getByText("120")).toBeVisible();
    expect(screen.getByText("35")).toBeVisible();
  });
});
