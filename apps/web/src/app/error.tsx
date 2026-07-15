"use client";

export default function ErrorPage({
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <main className="grid min-h-screen place-items-center bg-[var(--surface)] px-5 text-[var(--surface-foreground)]">
      <div>
        <h1 className="font-serif text-3xl">Halaman belum dapat dimuat.</h1>
        <p className="mt-3 text-[var(--muted)]">Silakan coba kembali.</p>
        <button
          className="mt-6 min-h-11 rounded-xl bg-[var(--primary)] px-5"
          onClick={reset}
        >
          Coba lagi
        </button>
      </div>
    </main>
  );
}
