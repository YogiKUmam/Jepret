import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReviewForm } from "./review-form";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ReviewForm", () => {
  it("renders star rating choices and submits review", async () => {
    const onSuccess = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            data: {
              id: "rev-1",
              booking_id: "book-1",
              client_user_id: "u-1",
              client_full_name: "Klien Test",
              creator_profile_id: "c-1",
              rating: 5,
              comment: "Bagus sekali!",
              created_at: "2026-08-28T00:00:00Z",
            },
          }),
      }),
    );

    render(<ReviewForm bookingId="book-1" onSuccess={onSuccess} />);

    expect(
      screen.getByRole("heading", { name: /beri ulasan untuk kreator/i }),
    ).toBeVisible();

    const commentInput = screen.getByPlaceholderText(/tulis ulasan anda/i);
    fireEvent.change(commentInput, { target: { value: "Bagus sekali!" } });

    const submitBtn = screen.getByRole("button", { name: /kirim ulasan/i });
    fireEvent.click(submitBtn);

    expect(await screen.findByText(/kirim ulasan/i)).toBeVisible();
    expect(onSuccess).toHaveBeenCalled();
  });
});
