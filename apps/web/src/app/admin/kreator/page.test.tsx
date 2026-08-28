import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminCreatorApplicationsPage from "./page";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AdminCreatorApplicationsPage", () => {
  it("renders applications and allows approving creator", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("/approve")) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () =>
              Promise.resolve({
                data: {
                  id: "prof-1",
                  display_name: "Lensa Indah",
                  status: "approved",
                },
              }),
          });
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              data: [
                {
                  profile: {
                    id: "prof-1",
                    display_name: "Lensa Indah",
                    city: "Surabaya",
                    bio: "Fotografer handal",
                    specialty: "portrait",
                    starting_price_idr: 800_000,
                    status: "pending",
                    submitted_at: "2026-08-28T00:00:00Z",
                    reviewed_at: null,
                  },
                  user_email: "lensa@jepret.local",
                  user_full_name: "Lensa Owner",
                },
              ],
            }),
        });
      }),
    );

    render(<AdminCreatorApplicationsPage />);

    expect(
      await screen.findByRole("heading", { name: "Lensa Indah" }),
    ).toBeVisible();
    expect(screen.getByText("Surabaya")).toBeVisible();

    const approveBtn = screen.getByRole("button", { name: /setujui profil/i });
    fireEvent.click(approveBtn);

    expect(
      await screen.findByText(/profil kreator berhasil disetujui/i),
    ).toBeVisible();
  });
});
