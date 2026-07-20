import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QueryProvider } from "@/lib/query-provider";

import DaftarPage from "./page";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

function renderPage() {
  return render(
    <QueryProvider>
      <DaftarPage />
    </QueryProvider>,
  );
}

beforeEach(() => {
  push.mockClear();
  vi.unstubAllGlobals();
});

describe("DaftarPage", () => {
  it("shows validation errors for empty submit", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: /daftar/i }));
    expect(await screen.findByText("Nama wajib diisi.")).toBeVisible();
    expect(screen.getByText("Email wajib diisi.")).toBeVisible();
    expect(screen.getByText("Password wajib diisi.")).toBeVisible();
  });

  it("registers and redirects to profile on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        json: () =>
          Promise.resolve({
            data: {
              id: "1",
              email: "uji@jepret.local",
              full_name: "Uji Web",
              is_admin: false,
              creator_profile: null,
            },
          }),
      }),
    );
    renderPage();
    await userEvent.type(screen.getByLabelText("Nama lengkap"), "Uji Web");
    await userEvent.type(screen.getByLabelText("Email"), "uji@jepret.local");
    await userEvent.type(screen.getByLabelText("Password"), "sandi-aman-123");
    await userEvent.click(screen.getByRole("button", { name: /daftar/i }));
    expect(await vi.waitFor(() => push.mock.calls[0][0])).toBe("/profil");
  });
});
