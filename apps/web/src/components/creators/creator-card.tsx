import Link from "next/link";

import type { CreatorPublic } from "@/lib/api";
import { formatIdr } from "@/lib/format";

export function CreatorCard({ creator }: { creator: CreatorPublic }) {
  return (
    <Link
      href={`/kreator/${creator.id}`}
      aria-label={creator.display_name}
      className="block"
    >
      <article className="overflow-hidden rounded-2xl bg-[var(--background)] text-[var(--foreground)]">
        <div
          aria-hidden
          className="grid h-40 place-items-center bg-[linear-gradient(135deg,#5b5148,#1f1d1b)]"
        >
          <span className="font-serif text-4xl text-[#cfc5b8]">
            {creator.display_name.charAt(0)}
          </span>
        </div>
        <div className="p-4">
          <p className="text-xs font-semibold text-[var(--primary)]">
            TERVERIFIKASI
          </p>
          <h3 className="mt-2 text-lg font-semibold">{creator.display_name}</h3>
          <p className="mt-1 text-sm text-[#cfc5b8]">
            {creator.city} · {creator.specialty}
          </p>
          <p className="mt-4 text-sm">
            Mulai {formatIdr(creator.starting_price_idr)}
          </p>
        </div>
      </article>
    </Link>
  );
}
