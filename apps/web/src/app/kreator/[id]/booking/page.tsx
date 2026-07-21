"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useForm } from "react-hook-form";

import { TextField } from "@/components/auth/text-field";
import { AppHeader } from "@/components/layout/app-header";
import { ApiError } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { useCreateBooking } from "@/lib/bookings";
import { useCreator } from "@/lib/creators";

interface BookingForm {
  event_date: string;
  event_city: string;
  notes: string;
}

export default function AjukanBookingPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { data: me, isPending: mePending } = useMe();
  const { data: creator } = useCreator(params.id);
  const createBooking = useCreateBooking();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<BookingForm>();

  useEffect(() => {
    if (!mePending && me === null) router.push("/masuk");
  }, [me, mePending, router]);

  async function onSubmit(values: BookingForm) {
    await createBooking.mutateAsync({
      creator_id: params.id,
      event_date: values.event_date,
      event_city: values.event_city,
      notes: values.notes ?? "",
    });
    router.push("/booking");
  }

  const serverError =
    createBooking.error instanceof ApiError
      ? createBooking.error.message
      : null;

  return (
    <main className="min-h-screen bg-[var(--surface)] pb-24 text-[var(--surface-foreground)]">
      <AppHeader />
      <section className="mx-auto max-w-md px-5 py-10">
        <h1 className="font-serif text-3xl">Ajukan booking</h1>
        {creator ? (
          <p className="mt-2 text-[var(--muted)]">{creator.display_name}</p>
        ) : null}
        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4">
          <TextField
            id="event_date"
            label="Tanggal acara"
            type="date"
            error={errors.event_date?.message}
            {...register("event_date", {
              required: "Tanggal acara wajib diisi.",
            })}
          />
          <TextField
            id="event_city"
            label="Kota acara"
            error={errors.event_city?.message}
            {...register("event_city", {
              required: "Kota acara wajib diisi.",
              minLength: { value: 2, message: "Kota acara terlalu pendek." },
            })}
          />
          <label className="block">
            <span className="mb-1 block text-sm font-medium">
              Catatan (opsional)
            </span>
            <textarea
              rows={4}
              className="w-full rounded-xl border border-[var(--border)] bg-white p-3"
              {...register("notes")}
            />
          </label>
          {serverError ? (
            <p role="alert" className="text-sm text-[#a33]">
              {serverError}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={createBooking.isPending}
            className="min-h-11 w-full rounded-xl bg-[var(--primary)] font-medium disabled:opacity-60"
          >
            {createBooking.isPending ? "Mengirim…" : "Kirim permintaan"}
          </button>
        </form>
      </section>
    </main>
  );
}
