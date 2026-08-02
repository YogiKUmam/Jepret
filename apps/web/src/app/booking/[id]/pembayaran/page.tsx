"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AppHeader } from "@/components/layout/app-header";
import { BottomNavigation } from "@/components/layout/bottom-navigation";
import {
  ApiError,
  type Booking,
  type PaymentStatus,
  type User,
} from "@/lib/api";
import { useMe } from "@/lib/auth";
import { useIncomingBookings, useMyBookings } from "@/lib/bookings";
import { formatIdr } from "@/lib/format";
import {
  useCreatePayment,
  usePayment,
  useSimulatePaid,
  useSimulateRelease,
} from "@/lib/payments";

const PAYMENT_STATUS_LABELS: Record<PaymentStatus, string> = {
  pending: "Menunggu pembayaran",
  paid: "Pembayaran diterima",
  held: "Dana tercatat aman",
  released: "Pembayaran telah dilepas",
  refunded: "Pembayaran dikembalikan",
  failed: "Pembayaran gagal",
  expired: "Pembayaran kedaluwarsa",
};

const actionClass =
  "min-h-11 w-full rounded-xl bg-[var(--primary)] px-5 py-3 text-sm font-medium text-[var(--primary-foreground)] disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto";
const retryClass =
  "mt-4 min-h-11 rounded-xl border border-[var(--border)] px-5 text-sm font-medium disabled:opacity-60";

function LoadingSkeleton() {
  return (
    <div aria-hidden className="mt-8 space-y-4">
      <div className="h-8 w-48 animate-pulse rounded-lg bg-[var(--border)]" />
      <div className="h-28 animate-pulse rounded-2xl bg-[var(--border)]" />
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="mt-8">
      <p role="alert" className="text-[var(--surface-foreground)]">
        {message}
      </p>
      <button type="button" onClick={onRetry} className={retryClass}>
        Coba lagi
      </button>
    </div>
  );
}

function PaymentDetails({
  booking,
  me,
  isIncoming,
}: {
  booking: Booking;
  me: User;
  isIncoming: boolean;
}) {
  const payment = usePayment(booking.id);
  const createPayment = useCreatePayment(booking.id);
  const paymentId = payment.data?.id ?? "";
  const simulatePaid = useSimulatePaid(paymentId, booking.id);
  const simulateRelease = useSimulateRelease(paymentId, booking.id);
  const [idempotencyKey] = useState(() => crypto.randomUUID());

  const notCreated =
    payment.error instanceof ApiError && payment.error.status === 404;
  const canCreate = notCreated && booking.status === "accepted" && !isIncoming;
  const canSimulatePaid = payment.data?.status === "pending" && !isIncoming;
  const canSimulateRelease =
    payment.data?.status === "held" &&
    booking.status === "completed" &&
    isIncoming &&
    me.creator_profile?.id === booking.creator.id;
  const mutationError =
    createPayment.isError || simulatePaid.isError || simulateRelease.isError;

  if (payment.isPending) {
    return <p className="mt-8 text-[var(--muted)]">Memuat pembayaran…</p>;
  }

  if (payment.isError && !notCreated) {
    return (
      <ErrorState
        message="Pembayaran belum dapat dimuat. Silakan coba lagi."
        onRetry={() => void payment.refetch()}
      />
    );
  }

  return (
    <div className="mt-8 space-y-8">
      <div>
        <p className="text-sm text-[var(--muted)]">Total pembayaran</p>
        <p className="mt-1 font-serif text-4xl">
          {formatIdr(payment.data?.amount_idr ?? booking.quoted_price_idr)}
        </p>
      </div>

      <div className="border-y border-[var(--border)] py-5">
        <p className="text-sm text-[var(--muted)]">Status</p>
        <p className="mt-1 text-lg font-medium">
          {payment.data
            ? PAYMENT_STATUS_LABELS[payment.data.status]
            : "Pembayaran belum dibuat"}
        </p>
      </div>

      <p className="rounded-xl bg-[var(--border)] px-4 py-3 text-sm font-medium">
        Pembayaran simulasi — tidak ada dana nyata yang diproses.
      </p>

      {mutationError ? (
        <p role="alert">Aksi pembayaran belum berhasil. Silakan coba lagi.</p>
      ) : null}

      {canCreate ? (
        <button
          type="button"
          className={actionClass}
          disabled={createPayment.isPending}
          onClick={() => {
            if (!createPayment.isPending) createPayment.mutate(idempotencyKey);
          }}
        >
          {createPayment.isPending ? "Membuat pembayaran…" : "Buat pembayaran"}
        </button>
      ) : canSimulatePaid ? (
        <button
          type="button"
          className={actionClass}
          disabled={simulatePaid.isPending}
          onClick={() => {
            if (!simulatePaid.isPending) simulatePaid.mutate();
          }}
        >
          {simulatePaid.isPending
            ? "Memproses simulasi…"
            : "Simulasikan pembayaran berhasil"}
        </button>
      ) : canSimulateRelease ? (
        <button
          type="button"
          className={actionClass}
          disabled={simulateRelease.isPending}
          onClick={() => {
            if (!simulateRelease.isPending) simulateRelease.mutate();
          }}
        >
          {simulateRelease.isPending
            ? "Memproses pencairan…"
            : "Simulasikan pencairan"}
        </button>
      ) : null}
    </div>
  );
}

function RelatedBooking({ bookingId, me }: { bookingId: string; me: User }) {
  const mine = useMyBookings();
  const incoming = useIncomingBookings();
  const myBooking = mine.data?.find((booking) => booking.id === bookingId);
  const incomingBooking = incoming.data?.find(
    (booking) => booking.id === bookingId,
  );
  const relatedBooking = myBooking ?? incomingBooking;

  if (!relatedBooking && (mine.isPending || incoming.isPending)) {
    return <LoadingSkeleton />;
  }

  if (!relatedBooking && (mine.isError || incoming.isError)) {
    return (
      <ErrorState
        message="Booking belum dapat dimuat. Silakan coba lagi."
        onRetry={() => {
          void mine.refetch();
          void incoming.refetch();
        }}
      />
    );
  }

  if (!relatedBooking) {
    return <p className="mt-8 text-[var(--muted)]">Booking tidak ditemukan.</p>;
  }

  return (
    <PaymentDetails
      booking={relatedBooking}
      me={me}
      isIncoming={!myBooking && Boolean(incomingBooking)}
    />
  );
}

export default function PaymentPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const me = useMe();

  useEffect(() => {
    if (!me.isPending && me.data === null) router.push("/masuk");
  }, [me.data, me.isPending, router]);

  return (
    <main className="min-h-screen bg-[var(--surface)] pb-24 text-[var(--surface-foreground)]">
      <AppHeader />
      <section className="mx-auto max-w-2xl px-5 py-10">
        <p className="text-sm font-medium text-[var(--primary)]">Sandbox</p>
        <h1 className="mt-2 font-serif text-3xl">Pembayaran booking</h1>
        {me.isPending ? (
          <LoadingSkeleton />
        ) : me.isError ? (
          <ErrorState
            message="Akun belum dapat diperiksa. Silakan coba lagi."
            onRetry={() => void me.refetch()}
          />
        ) : me.data ? (
          <RelatedBooking bookingId={params.id} me={me.data} />
        ) : null}
      </section>
      <BottomNavigation />
    </main>
  );
}
