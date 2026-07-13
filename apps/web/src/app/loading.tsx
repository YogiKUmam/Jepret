export default function Loading() {
  return (
    <main
      aria-busy="true"
      aria-label="Memuat halaman"
      className="min-h-screen animate-pulse bg-[var(--surface)]"
    />
  );
}
