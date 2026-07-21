import Link from "next/link";
import { CalendarDays, Compass, MessageCircle, UserRound } from "lucide-react";

const items = [
  ["Jelajah", Compass, "/"],
  ["Booking", CalendarDays, null],
  ["Chat", MessageCircle, null],
  ["Profil", UserRound, "/profil"],
] as const;

const itemClass =
  "flex min-h-14 flex-col items-center justify-center gap-1 text-xs";

export function BottomNavigation() {
  return (
    <nav
      aria-label="Navigasi utama"
      className="fixed inset-x-0 bottom-0 border-t border-[var(--border)] bg-[var(--surface)] md:hidden"
    >
      <ul className="mx-auto grid max-w-md grid-cols-4">
        {items.map(([label, Icon, href]) => (
          <li key={label}>
            {href ? (
              <Link href={href} className={itemClass}>
                <Icon aria-hidden size={18} />
                {label}
              </Link>
            ) : (
              <span className={itemClass}>
                <Icon aria-hidden size={18} />
                {label}
              </span>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}
