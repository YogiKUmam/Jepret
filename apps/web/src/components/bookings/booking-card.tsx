import type { Booking } from "@/lib/api";
import { BOOKING_STATUS_LABELS } from "@/lib/bookings";
import { formatIdr } from "@/lib/format";

const STATUS_CLASS: Record<string, string> = {
  requested: "bg-[#8a6d3b] text-white",
  accepted: "bg-[#2f6b4f] text-white",
  rejected: "bg-[#7a3b3b] text-white",
  completed: "bg-[#3b5a7a] text-white",
  cancelled: "bg-[var(--border)] text-[var(--foreground)]",
};

export function BookingCard({
  booking,
  children,
  showClient = false,
}: {
  booking: Booking;
  children?: React.ReactNode;
  showClient?: boolean;
}) {
  return (
    <article className="rounded-2xl bg-[var(--background)] p-4 text-[var(--foreground)]">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-lg font-semibold">
          {showClient ? booking.client_name : booking.creator.display_name}
        </h3>
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            STATUS_CLASS[booking.status] ?? ""
          }`}
        >
          {BOOKING_STATUS_LABELS[booking.status]}
        </span>
      </div>
      <p className="mt-2 text-sm text-[#cfc5b8]">
        {booking.event_date} · {booking.event_city}
      </p>
      {showClient ? (
        <p className="mt-1 text-sm text-[#cfc5b8]">
          Kreator: {booking.creator.display_name}
        </p>
      ) : null}
      {booking.notes ? <p className="mt-3 text-sm">{booking.notes}</p> : null}
      <p className="mt-3 text-sm font-medium">
        {formatIdr(booking.quoted_price_idr)}
      </p>
      {children ? <div className="mt-4 flex gap-3">{children}</div> : null}
    </article>
  );
}
