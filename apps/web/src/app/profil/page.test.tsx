import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QueryProvider } from "@/lib/query-provider";

import ProfilPage from "./page";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

beforeEach(() => {
  push.mockClear();
  vi.unstubAllGlobals();
});

function stubMe(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status < 400,
      status,
      json: () => Promise.resolve(body),
    }),
  );
}

describe("ProfilPage", () => {
  it("redirects to /masuk when unauthenticated", async () => {
    stubMe(401, {
      error: { code: "UNAUTHENTICATED", message: "Silakan masuk." },
    });
    render(
      <QueryProvider>
        <ProfilPage />
      </QueryProvider>,
    );
    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/masuk"));
  });

  it("shows user data and creator status when logged in", async () => {
    stubMe(200, {
      data: {
        id: "1",
        email: "kreator@jepret.local",
        full_name: "Kreator Demo",
        is_admin: false,
        creator_profile: {
          id: "2",
          display_name: "Studio Cahaya",
          city: "Bandung",
          bio: "",
          specialty: "wedding",
          starting_price_idr: 1500000,
          status: "approved",
          submitted_at: null,
          reviewed_at: null,
        },
      },
    });
    render(
      <QueryProvider>
        <ProfilPage />
      </QueryProvider>,
    );
    expect(await screen.findByText("kreator@jepret.local")).toBeVisible();
    expect(screen.getByDisplayValue("Kreator Demo")).toBeVisible();
    expect(screen.getByText(/Terverifikasi/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Keluar" })).toBeVisible();
  });
});
