import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("HomePage", () => {
  it("renders Indonesian discovery content and client navigation", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("heading", { name: /cerita yang layak diingat/i }),
    ).toBeVisible();
    expect(
      screen.getByRole("searchbox", { name: /cari kreator/i }),
    ).toHaveClass("min-h-11");
    expect(
      screen.getByRole("navigation", { name: /navigasi utama/i }),
    ).toBeVisible();
    expect(screen.getByText("Studio Cahaya")).toBeVisible();
  });
});
