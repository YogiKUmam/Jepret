import type { ReactNode } from "react";

import { AppHeader } from "@/components/layout/app-header";

export function AuthCard({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <main className="min-h-screen bg-[var(--surface)] pb-24 text-[var(--surface-foreground)]">
      <AppHeader />
      <section className="mx-auto max-w-md px-5 py-10">
        <h1 className="font-serif text-3xl">{title}</h1>
        {children}
      </section>
    </main>
  );
}
