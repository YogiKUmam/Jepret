import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DisputeModal } from "./dispute-modal";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DisputeModal", () => {
  it("renders modal and submits dispute when valid", async () => {
    const onSuccess = vi.fn();
    const onClose = vi.fn();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            data: {
              id: "disp-1",
              booking_id: "book-1",
              opened_by_user_id: "u-1",
              opened_by_full_name: "Klien Sengketa",
              reason_category: "not_delivered",
              description: "Kreator tidak hadir ke lokasi acara pernikahan.",
              status: "open",
              resolution_notes: null,
              resolved_by_admin_user_id: null,
              created_at: "2026-08-28T00:00:00Z",
              resolved_at: null,
            },
          }),
      }),
    );

    render(
      <DisputeModal
        bookingId="book-1"
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    expect(
      screen.getByRole("heading", { name: /ajukan sengketa \/ komplain/i }),
    ).toBeVisible();

    const descInput = screen.getByPlaceholderText(/jelaskan secara rinci/i);
    fireEvent.change(descInput, {
      target: { value: "Kreator tidak hadir ke lokasi acara pernikahan." },
    });

    const submitBtn = screen.getByRole("button", {
      name: /konfirmasi sengketa/i,
    });
    fireEvent.click(submitBtn);

    expect(await screen.findByText(/konfirmasi sengketa/i)).toBeVisible();
    expect(onSuccess).toHaveBeenCalled();
  });
});
