const idrFormatter = new Intl.NumberFormat("id-ID", {
  style: "currency",
  currency: "IDR",
  maximumFractionDigits: 0,
});

export function formatIdr(amount: number): string {
  return idrFormatter.format(amount);
}

export function formatDate(dateStr: string): string {
  try {
    return new Intl.DateTimeFormat("id-ID", {
      day: "numeric",
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(
      new Date(dateStr.includes("T") ? dateStr : `${dateStr}T00:00:00Z`),
    );
  } catch {
    return dateStr;
  }
}
