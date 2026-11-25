"use client";

// Live Cockpit sections as tabs under the program header (UX v1). Replaces the old
// release sidebar. Decision Studio is its own top-level screen, so it shows no tabs.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { releasePath } from "@/lib/routes";
import { COCKPIT_SECTIONS, cockpitSection } from "./model";

export function CockpitTabs({ project, release }: { project: string; release: string }) {
  const path = usePathname() ?? "";
  const here = cockpitSection(path);
  if (here === null) return null;
  return (
    <nav aria-label="Live Cockpit sections" className="flex flex-wrap gap-x-5 border-b border-slate-200">
      {COCKPIT_SECTIONS.map((s) => {
        const current = s.suffix === here;
        return (
          <Link
            key={s.label}
            href={releasePath(project, release, s.suffix)}
            aria-current={current ? "page" : undefined}
            className={`-mb-px inline-flex min-h-11 items-center border-b-2 px-1 text-sm ${
              current ? "border-action font-medium text-action" : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            {s.label}
          </Link>
        );
      })}
    </nav>
  );
}
