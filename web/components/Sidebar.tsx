"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// Simple 16px stroke icons (decorative; every item has a text label).
const ICONS: Record<string, React.ReactNode> = {
  Dashboard: <path d="M2 2h5v5H2zM9 2h5v5H9zM2 9h5v5H2zM9 9h5v5H9z" />,
  Dependencies: <path d="M4 3.5a1.5 1.5 0 1 0 0 .01M12 8a1.5 1.5 0 1 0 0 .01M4 12.5a1.5 1.5 0 1 0 0 .01M5.4 4.2l5.2 3M5.4 11.8l5.2-3" />,
  Simulations: <path d="M2 14V2M2 14h12M4.5 11l3-4 2.5 2 4-5" />,
  Reports: <path d="M4 1.5h6l3 3v10H4zM10 1.5v3h3M6 8h5M6 10.5h5" />,
  "Link review": <path d="M6.5 9.5l3-3M5 8l-1.5 1.5a2 2 0 0 0 3 3L8 11M11 8l1.5-1.5a2 2 0 0 0-3-3L8 5" />,
};

const ITEMS = [
  { href: "", label: "Dashboard" },
  { href: "/dependencies", label: "Dependencies" },
  { href: "/simulate", label: "Simulations" },
  { href: "/update", label: "Reports" },
  { href: "/links", label: "Link review" },
];

export function Sidebar({ release }: { release: string }) {
  const path = usePathname();
  const base = `/releases/${release}`;
  const active = (href: string) =>
    href === "" ? path === base || path.startsWith(`${base}/features`) : path.startsWith(base + href);
  return (
    <nav aria-label="Release sections" className="sticky top-4 flex flex-col gap-1 text-sm">
      <p className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-slate-400">{release}</p>
      {ITEMS.map((i) => (
        <Link
          key={i.label}
          href={base + i.href}
          aria-current={active(i.href) ? "page" : undefined}
          className={`flex items-center gap-2 rounded-md px-3 py-2 ${
            active(i.href) ? "bg-indigo-50 font-medium text-indigo-700" : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          <svg aria-hidden viewBox="0 0 16 16" className="h-4 w-4 fill-none stroke-current" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round">
            {ICONS[i.label]}
          </svg>
          {i.label}
        </Link>
      ))}
    </nav>
  );
}
