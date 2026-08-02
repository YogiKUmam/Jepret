"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { BookingCard } from "@/components/bookings/booking-card";
import { AppHeader } from "@/components/layout/app-header";
import { BottomNavigation } from "@/components/layout/bottom-navigation";
import { useMe } from "@/lib/auth";
import {
  ACTIVE_BOOKING_STATUSES,
  useBookingAction,
  useMyBookings,
} from "@/lib/bookings";

const primaryActionClass =
  "inline-flex min-h-11 items-center rounded-xl bg-[var(--primary)] px-5 text-sm font-medium text-[var(--primary-foreground)]";
const secondaryActionClass =
  "inline-flex min-h-11 items-center rounded-xl border border-[var(--border)] px-5 text-sm font-medium disabled:opacity-60";

export default function BookingPage() {
  const router = useRouter();
  const { data: me, isPending: mePending } = useMe();
  const bookings = useMyBookings();
  const cancel = useBookingAction("cancel");

  useEffect(() => {
    if (!mePending && me === null) router.push("/masuk");
  }, [me, mePending, router]);

  return (
    <main className="min-h-screen bg-[var(--surface)] pb-24 text-[var(--surface-foreground)]">
      <AppHeader />
      <section className="mx-auto max-w-3xl px-5 py-10">
        <div className="flex items-center justify-between gap-4">
          <h1 className="font-serif text-3xl">Booking saya</h1>
          {me?.creator_profile?.status === "approved" ? (
            <Link
              href="/booking/masuk"
              className="text-sm font-medium text-[var(--primary)]"
            >
              Booking masuk
            </Link>
          ) : null}
        </div>
        {cancel.isError ? (
          <p role="alert" className="mt-6 text-[var(--surface-foreground)]">
            Booking belum dapat dibatalkan. Silakan coba lagi.
          </p>
        ) : null}
        {bookings.isPending ? (
          <div aria-hidden className="mt-6 space-y-4">
            {[0, 1].map((index) => (
              <div
                key={index}
                className="h-40 animate-pulse rounded-2xl bg-[var(--border)]"
              />
            ))}
          </div>
        ) : bookings.isError ? (
          <p role="alert" className="mt-6 text-[var(--muted)]">
            Daftar booking belum dapat dimuat.
          </p>
        ) : bookings.data && bookings.data.length > 0 ? (
          <ul className="mt-6 list-none space-y-4">
            {bookings.data.map((booking) => (
              <li key={booking.id}>
                <BookingCard booking={booking}>
                  {booking.status === "accepted" ? (
                    <Link
                      href={`/booking/${booking.id}/pembayaran`}
                      className={primaryActionClass}
                    >
                      Bayar sekarang
                    </Link>
                  ) : booking.status === "awaiting_payment" ||
                    booking.status === "confirmed" ? (
                    <Link
                      href={`/booking/${booking.id}/pembayaran`}
                      className={secondaryActionClass}
                    >
                      Lihat pembayaran
                    </Link>
                  ) : null}
                  {ACTIVE_BOOKING_STATUSES.includes(booking.status) ? (
                    <button
                      type="button"
                      onClick={() => cancel.mutate(booking.id)}
                      disabled={cancel.isPending}
                      className={secondaryActionClass}
                    >
                      Batalkan
                    </button>
                  ) : null}
                </BookingCard>
              </li>
            ))}
          </ul>
        ) : (
          <div className="mt-6">
            <p className="text-[var(--muted)]">Belum ada booking.</p>
            <Link
              href="/"
              className="mt-3 inline-block font-medium text-[var(--primary)]"
            >
              Cari kreator
            </Link>
          </div>
        )}
      </section>
      <BottomNavigation />
    </main>
  );
}
