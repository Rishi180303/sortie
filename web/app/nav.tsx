"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/setup", label: "Setup" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/matches", label: "Matches" },
  { href: "/digest", label: "Digest" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="flex flex-wrap gap-6 pt-2 pb-6">
      {links.map((link) => {
        // startsWith so /digest/12 still lights up Digest; none of our hrefs are
        // "/" so this can't accidentally match every page
        const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={
              active
                ? "font-display text-[15px] font-bold text-snow underline decoration-orange decoration-[3px] underline-offset-[6px]"
                : "font-display text-[15px] font-bold text-sage no-underline"
            }
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
