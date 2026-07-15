export function CreatorPreviewCard() {
  return (
    <article className="mt-4 max-w-sm overflow-hidden rounded-2xl bg-[var(--background)] text-[var(--foreground)]">
      <div
        aria-hidden
        className="h-40 bg-[linear-gradient(135deg,#5b5148,#1f1d1b)]"
      />
      <div className="p-4">
        <p className="text-xs font-semibold text-[var(--primary)]">
          TERVERIFIKASI
        </p>
        <h3 className="mt-2 text-lg font-semibold">Studio Cahaya</h3>
        <p className="mt-1 text-sm text-[#cfc5b8]">Bandung · Wedding · ★ 4,9</p>
        <p className="mt-4 text-sm">Mulai Rp1.500.000</p>
      </div>
    </article>
  );
}
