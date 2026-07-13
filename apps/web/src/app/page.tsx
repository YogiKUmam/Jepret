import { CreatorPreviewCard } from "@/components/creators/creator-preview-card";
import { AppHeader } from "@/components/layout/app-header";
import { BottomNavigation } from "@/components/layout/bottom-navigation";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-[var(--surface)] pb-24 text-[var(--surface-foreground)]">
      <AppHeader />
      <section className="mx-auto max-w-6xl px-5 py-10">
        <p className="text-xs uppercase tracking-[0.18em] text-[var(--primary)]">Jepret</p>
        <h1 className="max-w-xl font-serif text-5xl leading-none">Cerita yang layak diingat.</h1>
        <p className="mt-5 max-w-xl text-[var(--muted)]">
          Temukan fotografer dan videografer terverifikasi untuk setiap momen.
        </p>
        <label className="mt-7 block max-w-xl">
          <span className="sr-only">Cari kreator</span>
          <input
            type="search"
            aria-label="Cari kreator"
            className="min-h-11 w-full rounded-xl border border-[var(--border)] bg-white px-4"
            placeholder="Cari gaya, kota, atau kebutuhan"
          />
        </label>
      </section>
      <section aria-labelledby="creator-heading" className="mx-auto max-w-6xl px-5">
        <h2 id="creator-heading" className="font-serif text-2xl">
          Pilihan di dekatmu
        </h2>
        <CreatorPreviewCard />
      </section>
      <BottomNavigation />
    </main>
  );
}
