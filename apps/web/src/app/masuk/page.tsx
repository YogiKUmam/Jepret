"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";

import { AuthCard } from "@/components/auth/auth-card";
import { TextField } from "@/components/auth/text-field";
import { ApiError } from "@/lib/api";
import { useLogin } from "@/lib/auth";

interface LoginForm {
  email: string;
  password: string;
}

export default function MasukPage() {
  const router = useRouter();
  const login = useLogin();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>();

  const onSubmit = handleSubmit((values) =>
    login.mutate(values, { onSuccess: () => router.push("/profil") }),
  );

  const serverError =
    login.error instanceof ApiError
      ? login.error.message
      : login.error
        ? "Terjadi kesalahan. Silakan coba lagi."
        : null;

  return (
    <AuthCard title="Masuk ke Jepret">
      <form onSubmit={onSubmit} noValidate>
        <TextField
          id="email"
          type="email"
          label="Email"
          autoComplete="email"
          error={errors.email?.message}
          {...register("email", {
            required: "Email wajib diisi.",
            pattern: {
              value: /^[^@\s]+@[^@\s]+\.[^@\s]+$/,
              message: "Format email tidak valid.",
            },
          })}
        />
        <TextField
          id="password"
          type="password"
          label="Password"
          autoComplete="current-password"
          error={errors.password?.message}
          {...register("password", { required: "Password wajib diisi." })}
        />
        {serverError ? (
          <p role="alert" className="mt-4 text-sm text-[var(--destructive)]">
            {serverError}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={login.isPending}
          className="mt-6 min-h-11 w-full rounded-xl bg-[var(--primary)] px-5 font-medium text-[var(--primary-foreground)] disabled:opacity-60"
        >
          {login.isPending ? "Memproses…" : "Masuk"}
        </button>
      </form>
      <p className="mt-6 text-sm text-[var(--muted)]">
        Belum punya akun?{" "}
        <Link href="/daftar" className="font-medium text-[var(--primary)]">
          Daftar
        </Link>
      </p>
    </AuthCard>
  );
}
