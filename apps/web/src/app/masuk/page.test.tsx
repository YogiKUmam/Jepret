import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QueryProvider } from "@/lib/query-provider";

import MasukPage from "./page";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

beforeEach(() => {
  push.mockClear();
  vi.unstubAllGlobals();
});

describe("MasukPage", () => {
  it("shows the API error message on invalid credentials", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: () =>
          Promise.resolve({
            error: {
              code: "INVALID_CREDENTIALS",
              message: "Email atau password salah.",
            },
          }),
      }),
    );
    render(
      <QueryProvider>
        <MasukPage />
      </QueryProvider>,
    );
    await userEvent.type(screen.getByLabelText("Email"), "salah@jepret.local");
    await userEvent.type(screen.getByLabelText("Password"), "salah-total");
    await userEvent.click(screen.getByRole("button", { name: /masuk/i }));
    expect(await screen.findByText("Email atau password salah.")).toBeVisible();
    expect(push).not.toHaveBeenCalled();
  });
});
