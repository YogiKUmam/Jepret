"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";

import { AuthCard } from "@/components/auth/auth-card";
import { TextField } from "@/components/auth/text-field";
import { ApiError } from "@/lib/api";
import { useRegister } from "@/lib/auth";

interface RegisterForm {
  full_name: string;
  email: string;
  password: string;
}

export default function DaftarPage() {
  const router = useRouter();
  const registerUser = useRegister();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterForm>();

  const onSubmit = handleSubmit((values) =>
    registerUser.mutate(values, { onSuccess: () => router.push("/profil") }),
  );

  const serverError =
    registerUser.error instanceof ApiError
      ? registerUser.error.message
      : registerUser.error
        ? "Terjadi kesalahan. Silakan coba lagi."
        : null;

  return (
    <AuthCard title="Buat akun Jepret">
      <form onSubmit={onSubmit} noValidate>
        <TextField
          id="full_name"
          type="text"
          label="Nama lengkap"
          autoComplete="name"
          error={errors.full_name?.message}
          {...register("full_name", {
            required: "Nama wajib diisi.",
            minLength: { value: 2, message: "Nama minimal 2 karakter." },
          })}
        />
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
          autoComplete="new-password"
          error={errors.password?.message}
          {...register("password", {
            required: "Password wajib diisi.",
            minLength: { value: 8, message: "Password minimal 8 karakter." },
          })}
        />
        {serverError ? (
          <p role="alert" className="mt-4 text-sm text-[var(--destructive)]">
            {serverError}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={registerUser.isPending}
          className="mt-6 min-h-11 w-full rounded-xl bg-[var(--primary)] px-5 font-medium text-[var(--primary-foreground)] disabled:opacity-60"
        >
          {registerUser.isPending ? "Memproses…" : "Daftar"}
        </button>
      </form>
      <p className="mt-6 text-sm text-[var(--muted)]">
        Sudah punya akun?{" "}
        <Link href="/masuk" className="font-medium text-[var(--primary)]">
          Masuk
        </Link>
      </p>
    </AuthCard>
  );
}
