export function AppHeader() {
  return (
    <header className="border-b border-[var(--border)] bg-[var(--surface)]">
      <div className="mx-auto flex min-h-14 max-w-6xl items-center justify-between px-5">
        <span className="text-sm font-bold tracking-[0.18em]">JEPRET</span>
        <span className="text-sm text-[var(--muted)]">Bandung</span>
      </div>
    </header>
  );
}
