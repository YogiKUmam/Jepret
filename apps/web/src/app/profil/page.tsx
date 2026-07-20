"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useForm } from "react-hook-form";

import { TextField } from "@/components/auth/text-field";
import { AppHeader } from "@/components/layout/app-header";
import { BottomNavigation } from "@/components/layout/bottom-navigation";
import { CreatorStatusCard } from "@/components/profile/creator-status-card";
import { useLogout, useMe, useUpdateProfile } from "@/lib/auth";

interface ProfileForm {
  full_name: string;
}

export default function ProfilPage() {
  const router = useRouter();
  const me = useMe();
  const logout = useLogout();
  const updateProfile = useUpdateProfile();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ProfileForm>();

  useEffect(() => {
    if (me.data) reset({ full_name: me.data.full_name });
  }, [me.data, reset]);

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
  if (me.isError) {
    return (
      <main className="grid min-h-screen place-items-center bg-[var(--surface)] px-5 text-[var(--surface-foreground)]">
        <p role="alert">Profil belum dapat dimuat. Silakan muat ulang.</p>
      </main>
    );
  }
  if (!me.data) return null;

  const onSubmit = handleSubmit((values) => updateProfile.mutate(values));

  return (
    <main className="min-h-screen bg-[var(--surface)] pb-24 text-[var(--surface-foreground)]">
      <AppHeader />
      <section className="mx-auto max-w-md px-5 py-10">
        <h1 className="font-serif text-3xl">Profil saya</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">{me.data.email}</p>

        <form onSubmit={onSubmit} noValidate className="mt-6">
          <TextField
            id="full_name"
            type="text"
            label="Nama lengkap"
            error={errors.full_name?.message}
            {...register("full_name", {
              required: "Nama wajib diisi.",
              minLength: { value: 2, message: "Nama minimal 2 karakter." },
            })}
          />
          <button
            type="submit"
            disabled={updateProfile.isPending}
            className="mt-4 min-h-11 rounded-xl bg-[var(--primary)] px-5 font-medium text-[var(--primary-foreground)] disabled:opacity-60"
          >
            {updateProfile.isPending ? "Menyimpan…" : "Simpan nama"}
          </button>
          {updateProfile.isSuccess ? (
            <p role="status" className="mt-2 text-sm text-[var(--success)]">
              Nama tersimpan.
            </p>
          ) : null}
        </form>

        <CreatorStatusCard profile={me.data.creator_profile} />

        <button
          type="button"
          onClick={() =>
            logout.mutate(undefined, { onSuccess: () => router.push("/masuk") })
          }
          disabled={logout.isPending}
          className="mt-8 min-h-11 w-full rounded-xl border border-[var(--destructive)] px-5 font-medium text-[var(--destructive)] disabled:opacity-60"
        >
          Keluar
        </button>
      </section>
      <BottomNavigation />
    </main>
  );
}
