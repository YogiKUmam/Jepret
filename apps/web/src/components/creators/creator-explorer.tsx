"use client";

import { useState, type FormEvent } from "react";

import { useCreatorsInfinite, type CreatorFilters } from "@/lib/creators";

import { CreatorCard } from "./creator-card";

export function CreatorExplorer() {
  const [q, setQ] = useState("");
  const [city, setCity] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [filters, setFilters] = useState<CreatorFilters>({});
  const query = useCreatorsInfinite(filters);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters({
      q: q.trim() || undefined,
      city: city.trim() || undefined,
      specialty: specialty.trim() || undefined,
    });
  }

  const creators = query.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <>
      <section className="mx-auto max-w-6xl px-5 py-10">
        <p className="text-xs uppercase tracking-[0.18em] text-[var(--primary)]">
          Jepret
        </p>
        <h1 className="max-w-xl font-serif text-5xl leading-none">
          Cerita yang layak diingat.
        </h1>
        <p className="mt-5 max-w-xl text-[var(--muted)]">
          Temukan fotografer dan videografer terverifikasi untuk setiap momen.
        </p>
        <form onSubmit={applyFilters} className="mt-7 max-w-xl space-y-3">
          <label className="block">
            <span className="sr-only">Cari kreator</span>
            <input
              type="search"
              aria-label="Cari kreator"
              value={q}
              onChange={(event) => setQ(event.target.value)}
              className="min-h-11 w-full rounded-xl border border-[var(--border)] bg-white px-4"
              placeholder="Cari gaya, kota, atau kebutuhan"
            />
          </label>
          <div className="flex flex-wrap gap-3">
            <input
              aria-label="Kota"
              value={city}
              onChange={(event) => setCity(event.target.value)}
              className="min-h-11 min-w-0 flex-1 rounded-xl border border-[var(--border)] bg-white px-4"
              placeholder="Kota"
            />
            <input
              aria-label="Spesialisasi"
              value={specialty}
              onChange={(event) => setSpecialty(event.target.value)}
              className="min-h-11 min-w-0 flex-1 rounded-xl border border-[var(--border)] bg-white px-4"
              placeholder="Spesialisasi"
            />
            <button
              type="submit"
              className="min-h-11 rounded-xl bg-[var(--primary)] px-5 font-medium"
            >
              Terapkan
            </button>
          </div>
        </form>
      </section>
      <section
        aria-labelledby="creator-heading"
        className="mx-auto max-w-6xl px-5"
      >
        <h2 id="creator-heading" className="font-serif text-2xl">
          Pilihan di dekatmu
        </h2>
        {query.isPending ? (
          <div
            aria-hidden
            className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
          >
            {[0, 1, 2].map((index) => (
              <div
                key={index}
                className="h-64 animate-pulse rounded-2xl bg-[var(--border)]"
              />
            ))}
          </div>
        ) : query.isError ? (
          <p role="alert" className="mt-4 text-[var(--muted)]">
            Daftar kreator belum dapat dimuat. Silakan coba kembali.
          </p>
        ) : creators.length === 0 ? (
          <p className="mt-4 text-[var(--muted)]">
            Tidak ada kreator yang cocok.
          </p>
        ) : (
          <ul className="mt-4 grid list-none gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {creators.map((creator) => (
              <li key={creator.id}>
                <CreatorCard creator={creator} />
              </li>
            ))}
          </ul>
        )}
        {query.hasNextPage ? (
          <div className="mt-6 flex justify-center">
            <button
              type="button"
              onClick={() => query.fetchNextPage()}
              disabled={query.isFetchingNextPage}
              className="min-h-11 rounded-xl border border-[var(--border)] px-6 font-medium disabled:opacity-60"
            >
              {query.isFetchingNextPage ? "Memuat…" : "Muat lebih"}
            </button>
          </div>
        ) : null}
      </section>
    </>
  );
}
