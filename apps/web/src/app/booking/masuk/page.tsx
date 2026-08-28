"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";

import { BookingCard } from "@/components/bookings/booking-card";
import { AppHeader } from "@/components/layout/app-header";
import { BottomNavigation } from "@/components/layout/bottom-navigation";
import { useMe } from "@/lib/auth";
import { useBookingAction, useIncomingBookings } from "@/lib/bookings";
import { useUnreadCounts } from "@/lib/conversations";

const primaryActionClass =
  "inline-flex min-h-11 items-center rounded-xl bg-[var(--primary)] px-5 text-sm font-medium text-[var(--primary-foreground)] shadow-sm transition active:scale-[0.98]";
const secondaryActionClass =
  "inline-flex min-h-11 items-center rounded-xl border border-[var(--border)] px-5 text-sm font-medium transition active:scale-[0.98] disabled:opacity-60";

const WORKSPACE_STATUSES = [
  "confirmed",
  "in_progress",
  "delivered",
  "completed",
];

export default function BookingMasukPage() {
  const router = useRouter();
  const { data: me, isPending: mePending } = useMe();
  const incoming = useIncomingBookings();
  const unreadQuery = useUnreadCounts();
  const accept = useBookingAction("accept");
  const reject = useBookingAction("reject");

  useEffect(() => {
    if (!mePending && me === null) router.push("/masuk");
  }, [me, mePending, router]);

  const unreadMap = useMemo(() => {
    const map = new Map<string, number>();
    if (unreadQuery.data) {
      for (const item of unreadQuery.data) {
        map.set(item.booking_id, item.count);
      }
    }
    return map;
  }, [unreadQuery.data]);

  const busy = accept.isPending || reject.isPending;

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
                <BookingCard
                  booking={booking}
                  showClient
                  unreadCount={unreadMap.get(booking.id) ?? 0}
                >
                  {booking.status === "requested" ? (
                    <>
                      <button
                        type="button"
                        onClick={() => accept.mutate(booking.id)}
                        disabled={busy}
                        className={`${primaryActionClass}`}
                      >
                        Terima
                      </button>
                      <button
                        type="button"
                        onClick={() => reject.mutate(booking.id)}
                        disabled={busy}
                        className={`${secondaryActionClass}`}
                      >
                        Tolak
                      </button>
                    </>
                  ) : WORKSPACE_STATUSES.includes(booking.status) ? (
                    <>
                      <Link
                        href={`/booking/${booking.id}`}
                        className={primaryActionClass}
                      >
                        Buka ruang kerja
                      </Link>
                      <Link
                        href={`/booking/${booking.id}/pembayaran`}
                        className={secondaryActionClass}
                      >
                        Lihat pembayaran
                      </Link>
                    </>
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
