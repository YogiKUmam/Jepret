"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useMe } from "@/lib/auth";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { data: me, isPending } = useMe();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isPending && (!me || !me.is_admin)) {
      router.push("/masuk");
    }
  }, [me, isPending, router]);

  if (isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--surface)] text-[var(--foreground)]">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
      </div>
    );
  }

  if (!me || !me.is_admin) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--surface)] p-6 text-center text-[var(--foreground)]">
        <div className="rounded-3xl border border-red-500/20 bg-red-500/10 p-8 max-w-md">
          <h1 className="font-serif text-2xl font-bold text-red-400">
            Akses Ditolak
          </h1>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Halaman ini hanya dapat diakses oleh administrator Jepret.
          </p>
          <Link
            href="/"
            className="mt-6 inline-block rounded-xl bg-[var(--primary)] px-6 py-2.5 text-sm font-semibold text-black"
          >
            Kembali ke Beranda
          </Link>
        </div>
      </div>
    );
  }

  const navItems = [
    { href: "/admin", label: "Ringkasan" },
    { href: "/admin/kreator", label: "Verifikasi Kreator" },
    { href: "/admin/sengketa", label: "Sengketa" },
  ];

  return (
    <div className="min-h-screen bg-[var(--surface)] text-[var(--foreground)]">
      {/* Admin Top Header Navigation Island */}
      <header className="sticky top-0 z-40 border-b border-white/[0.08] bg-[#1C1C1E]/80 backdrop-blur-2xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3.5 sm:px-6">
          <div className="flex items-center gap-6">
            <Link href="/admin" className="flex items-center gap-2">
              <span className="font-serif text-xl font-bold tracking-tight text-[var(--foreground)]">
                Jepret<span className="text-[var(--primary)]">.Admin</span>
              </span>
            </Link>

            <nav className="hidden sm:flex items-center gap-1">
              {navItems.map((item) => {
                const isActive = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`rounded-xl px-3.5 py-1.5 text-xs font-semibold transition-all ${
                      isActive
                        ? "bg-white/[0.1] text-white"
                        : "text-[var(--muted)] hover:text-white"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs text-[var(--muted)] hidden md:inline">
              Admin:{" "}
              <span className="font-semibold text-white">{me.full_name}</span>
            </span>
            <Link
              href="/"
              className="rounded-xl border border-white/[0.1] px-3 py-1.5 text-xs font-medium text-[var(--muted)] hover:text-white"
            >
              Kembali ke App
            </Link>
          </div>
        </div>

        {/* Mobile Admin Nav */}
        <div className="flex sm:hidden border-t border-white/[0.05] px-4 py-2 gap-2 overflow-x-auto">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`whitespace-nowrap rounded-lg px-3 py-1 text-xs font-semibold ${
                  isActive ? "bg-white/[0.1] text-white" : "text-[var(--muted)]"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">{children}</main>
    </div>
  );
}
