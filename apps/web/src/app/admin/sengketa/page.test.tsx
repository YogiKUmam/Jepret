import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminDisputesPage from "./page";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AdminDisputesPage", () => {
  it("renders disputes and allows admin to resolve dispute", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("/resolve")) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () =>
              Promise.resolve({
                data: {
                  id: "disp-1",
                  booking_id: "book-1",
                  opened_by_user_id: "u-1",
                  opened_by_full_name: "Klien Komplain",
                  reason_category: "not_delivered",
                  description: "Kreator tidak datang ke lokasi.",
                  status: "resolved_client",
                  resolution_notes:
                    "Refund disetujui karena kreator terbukti berhalangan.",
                  resolved_by_admin_user_id: "admin-1",
                  created_at: "2026-08-28T00:00:00Z",
                  resolved_at: "2026-08-28T01:00:00Z",
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
                  id: "disp-1",
                  booking_id: "book-1",
                  opened_by_user_id: "u-1",
                  opened_by_full_name: "Klien Komplain",
                  reason_category: "not_delivered",
                  description: "Kreator tidak datang ke lokasi.",
                  status: "open",
                  resolution_notes: null,
                  resolved_by_admin_user_id: null,
                  created_at: "2026-08-28T00:00:00Z",
                  resolved_at: null,
                },
              ],
            }),
        });
      }),
    );

    render(<AdminDisputesPage />);

    expect(
      await screen.findByRole("heading", {
        name: /hasil tidak diserahkan/i,
      }),
    ).toBeVisible();

    const openMediationBtn = screen.getByRole("button", {
      name: /buka mediasi \/ putusan/i,
    });
    fireEvent.click(openMediationBtn);

    const notesInput = screen.getByPlaceholderText(
      /jelaskan alasan dan bukti/i,
    );
    fireEvent.change(notesInput, {
      target: {
        value: "Refund disetujui karena kreator terbukti berhalangan.",
      },
    });

    const confirmBtn = screen.getByRole("button", {
      name: /konfirmasi keputusan/i,
    });
    fireEvent.click(confirmBtn);

    expect(
      await screen.findByText(/sengketa berhasil diselesaikan/i),
    ).toBeVisible();
  });
});
