import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { QueryProvider } from "./query-provider";
import { creatorListPath, useCreator, useCreatorsInfinite } from "./creators";

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryProvider>{children}</QueryProvider>
);

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("creatorListPath", () => {
  it("serializes only active filters plus cursor", () => {
    expect(creatorListPath({})).toBe("/creators");
    expect(
      creatorListPath({ q: "studio", city: "", max_price: 500000 }, "abc"),
    ).toBe("/creators?q=studio&max_price=500000&cursor=abc");
  });
});

describe("useCreatorsInfinite", () => {
  it("collects pages through next_cursor", async () => {
    const pageOne = {
      items: [{ id: "a" }, { id: "b" }],
      next_cursor: "next-1",
    };
    const pageTwo = { items: [{ id: "c" }], next_cursor: null };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(200, { data: pageOne }))
      .mockResolvedValueOnce(jsonResponse(200, { data: pageTwo }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useCreatorsInfinite({ q: "studio" }), {
      wrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.hasNextPage).toBe(true);

    await result.current.fetchNextPage();
    await waitFor(() =>
      expect(
        result.current.data?.pages.flatMap((page) => page.items),
      ).toHaveLength(3),
    );
    expect(result.current.hasNextPage).toBe(false);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/creators?q=studio&cursor=next-1",
      expect.anything(),
    );
  });
});

describe("useCreator", () => {
  it("returns the creator on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(200, { data: { id: "x", display_name: "Studio Uji" } }),
        ),
    );
    const { result } = renderHook(() => useCreator("x"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.display_name).toBe("Studio Uji");
  });

  it("maps 404 to null instead of an error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(404, {
          error: { code: "NOT_FOUND", message: "Kreator tidak ditemukan." },
        }),
      ),
    );
    const { result } = renderHook(() => useCreator("hilang"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
  });
});
