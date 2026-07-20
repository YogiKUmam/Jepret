import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "./api";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
  it("unwraps the data envelope on success", async () => {
    const fn = mockFetch(200, { data: { status: "ok" } });
    const result = await apiFetch<{ status: string }>("/auth/me");
    expect(result).toEqual({ status: "ok" });
    expect(fn).toHaveBeenCalledWith(
      "/api/v1/auth/me",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("throws ApiError with code from the error envelope", async () => {
    mockFetch(401, {
      error: {
        code: "INVALID_CREDENTIALS",
        message: "Email atau password salah.",
      },
    });
    const attempt = apiFetch("/auth/login", { method: "POST", body: "{}" });
    await expect(attempt).rejects.toMatchObject({
      code: "INVALID_CREDENTIALS",
      status: 401,
    });
    await expect(
      apiFetch("/auth/login", { method: "POST", body: "{}" }).catch((e) => e),
    ).resolves.toBeInstanceOf(ApiError);
  });

  it("falls back to UNKNOWN_ERROR when the body is not an envelope", async () => {
    mockFetch(500, null);
    await expect(apiFetch("/auth/me")).rejects.toMatchObject({
      code: "UNKNOWN_ERROR",
      status: 500,
    });
  });
});
