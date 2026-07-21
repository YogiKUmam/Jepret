"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { BookingCard } from "@/components/bookings/booking-card";
import { AppHeader } from "@/components/layout/app-header";
import { BottomNavigation } from "@/components/layout/bottom-navigation";
import { useMe } from "@/lib/auth";
import { useBookingAction, useIncomingBookings } from "@/lib/bookings";

const actionClass =
  "min-h-11 rounded-xl px-5 text-sm font-medium disabled:opacity-60";

export default function BookingMasukPage() {
  const router = useRouter();
  const { data: me, isPending: mePending } = useMe();
  const incoming = useIncomingBookings();
  const accept = useBookingAction("accept");
  const reject = useBookingAction("reject");
  const complete = useBookingAction("complete");

  useEffect(() => {
    if (!mePending && me === null) router.push("/masuk");
  }, [me, mePending, router]);

  const busy = accept.isPending || reject.isPending || complete.isPending;

  return (
    <main className="min-h-screen bg-[var(--surface)] pb-24 text-[var(--surface-foreground)]">
      <AppHeader />
      <section className="mx-auto max-w-3xl px-5 py-10">
        <h1 className="font-serif text-3xl">Booking masuk</h1>
        {incoming.isPending ? (
          <div aria-hidden className="mt-6 space-y-4">
            {[0, 1].map((index) => (
              <div
                key={index}
                className="h-40 animate-pulse rounded-2xl bg-[var(--border)]"
              />
            ))}
          </div>
        ) : incoming.isError ? (
          <p role="alert" className="mt-6 text-[var(--muted)]">
            Booking masuk belum dapat dimuat.
          </p>
        ) : incoming.data && incoming.data.length > 0 ? (
          <ul className="mt-6 list-none space-y-4">
            {incoming.data.map((booking) => (
              <li key={booking.id}>
                <BookingCard booking={booking} showClient>
                  {booking.status === "requested" ? (
                    <>
                      <button
                        type="button"
                        onClick={() => accept.mutate(booking.id)}
                        disabled={busy}
                        className={`${actionClass} bg-[var(--primary)]`}
                      >
                        Terima
                      </button>
                      <button
                        type="button"
                        onClick={() => reject.mutate(booking.id)}
                        disabled={busy}
                        className={`${actionClass} border border-[var(--border)]`}
                      >
                        Tolak
                      </button>
                    </>
                  ) : booking.status === "accepted" ? (
                    <button
                      type="button"
                      onClick={() => complete.mutate(booking.id)}
                      disabled={busy}
                      className={`${actionClass} border border-[var(--border)]`}
                    >
                      Tandai selesai
                    </button>
                  ) : null}
                </BookingCard>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-6 text-[var(--muted)]">Belum ada booking masuk.</p>
        )}
      </section>
      <BottomNavigation />
    </main>
  );
}
