"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useForm } from "react-hook-form";

import { TextField } from "@/components/auth/text-field";
import { AppHeader } from "@/components/layout/app-header";
import { BottomNavigation } from "@/components/layout/bottom-navigation";
import { ApiError } from "@/lib/api";
import {
  useMe,
  useSaveCreatorDraft,
  useSubmitCreatorProfile,
  type CreatorDraftInput,
} from "@/lib/auth";

export default function KreatorPage() {
  const router = useRouter();
  const me = useMe();
  const saveDraft = useSaveCreatorDraft();
  const submitProfile = useSubmitCreatorProfile();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreatorDraftInput>();

  const profile = me.data?.creator_profile ?? null;
  const editable =
    !profile || profile.status === "draft" || profile.status === "rejected";

  useEffect(() => {
    if (profile) {
      reset({
        display_name: profile.display_name,
        city: profile.city,
        bio: profile.bio,
        specialty: profile.specialty,
        starting_price_idr: profile.starting_price_idr,
      });
    }
  }, [profile, reset]);

  useEffect(() => {
    if (!me.isPending && me.data === null) router.push("/masuk");
  }, [me.isPending, me.data, router]);

  if (me.isPending) {
    return (
      <main
        aria-busy="true"
        className="min-h-screen animate-pulse bg-[var(--surface)]"
      />
    );
  }
  if (!me.data) return null;

  const onSubmit = handleSubmit((values) =>
    saveDraft.mutate({
      ...values,
      starting_price_idr: Number(values.starting_price_idr),
    }),
  );

  const mutationError = [saveDraft.error, submitProfile.error].find(Boolean);
  const serverError =
    mutationError instanceof ApiError
      ? mutationError.message
      : mutationError
        ? "Terjadi kesalahan. Silakan coba lagi."
        : null;

  return (
    <main className="min-h-screen bg-[var(--surface)] pb-24 text-[var(--surface-foreground)]">
      <AppHeader />
      <section className="mx-auto max-w-md px-5 py-10">
        <Link href="/profil" className="text-sm text-[var(--muted)]">
          ← Kembali ke profil
        </Link>
        <h1 className="mt-2 font-serif text-3xl">Profil kreator</h1>

        {profile?.status === "pending" ? (
          <p role="status" className="mt-4 rounded-xl bg-white p-4 text-sm">
            Pengajuanmu sedang{" "}
            <span className="font-semibold">menunggu verifikasi</span>. Profil
            tidak dapat diubah sampai proses selesai.
          </p>
        ) : null}
        {profile?.status === "approved" ? (
          <p role="status" className="mt-4 rounded-xl bg-white p-4 text-sm">
            Profilmu sudah <span className="font-semibold">terverifikasi</span>.
            🎉
          </p>
        ) : null}
        {profile?.status === "rejected" ? (
          <p role="alert" className="mt-4 rounded-xl bg-white p-4 text-sm">
            Pengajuan sebelumnya <span className="font-semibold">ditolak</span>.
            Perbaiki datamu lalu ajukan ulang.
          </p>
        ) : null}

        <form onSubmit={onSubmit} noValidate className="mt-4">
          <fieldset disabled={!editable} className="disabled:opacity-60">
            <TextField
              id="display_name"
              type="text"
              label="Nama studio / kreator"
              error={errors.display_name?.message}
              {...register("display_name", {
                required: "Nama kreator wajib diisi.",
                minLength: { value: 2, message: "Minimal 2 karakter." },
              })}
            />
            <TextField
              id="city"
              type="text"
              label="Kota"
              error={errors.city?.message}
              {...register("city", { required: "Kota wajib diisi." })}
            />
            <TextField
              id="specialty"
              type="text"
              label="Spesialisasi (mis. wedding, produk)"
              error={errors.specialty?.message}
              {...register("specialty", {
                required: "Spesialisasi wajib diisi.",
              })}
            />
            <TextField
              id="starting_price_idr"
              type="number"
              label="Harga mulai (Rp)"
              min={0}
              error={errors.starting_price_idr?.message}
              {...register("starting_price_idr", {
                required: "Harga mulai wajib diisi.",
                min: { value: 0, message: "Harga tidak boleh negatif." },
              })}
            />
            <div className="mt-4">
              <label htmlFor="bio" className="block text-sm font-medium">
                Bio singkat
              </label>
              <textarea
                id="bio"
                rows={4}
                className="mt-1 w-full rounded-xl border border-[var(--border)] bg-white px-4 py-3"
                {...register("bio")}
              />
            </div>
          </fieldset>

          {serverError ? (
            <p role="alert" className="mt-4 text-sm text-[var(--destructive)]">
              {serverError}
            </p>
          ) : null}

          {editable ? (
            <div className="mt-6 flex flex-col gap-3">
              <button
                type="submit"
                disabled={saveDraft.isPending}
                className="min-h-11 rounded-xl border border-[var(--primary)] px-5 font-medium text-[var(--primary)] disabled:opacity-60"
              >
                {saveDraft.isPending ? "Menyimpan…" : "Simpan draft"}
              </button>
              {profile?.status === "draft" ? (
                <button
                  type="button"
                  onClick={() => submitProfile.mutate()}
                  disabled={submitProfile.isPending}
                  className="min-h-11 rounded-xl bg-[var(--primary)] px-5 font-medium text-[var(--primary-foreground)] disabled:opacity-60"
                >
                  {submitProfile.isPending
                    ? "Mengajukan…"
                    : "Ajukan verifikasi"}
                </button>
              ) : null}
            </div>
          ) : null}
          {saveDraft.isSuccess && profile?.status !== "pending" ? (
            <p role="status" className="mt-3 text-sm text-[var(--success)]">
              Draft tersimpan.
            </p>
          ) : null}
        </form>
      </section>
      <BottomNavigation />
    </main>
  );
}
