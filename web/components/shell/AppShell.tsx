"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { releaseFromPath, releaseHref } from "@/lib/releasePath";

const NAV = [
  { section: "dashboard" as const, label: "Dashboard", icon: "▦" },
  { section: "dependencies" as const, label: "Dependencies", icon: "⧉" },
  { section: "simulator" as const, label: "Simulator", icon: "◎" },
  { section: "reports" as const, label: "Reports", icon: "☰" },
];

function activeSection(pathname: string): (typeof NAV)[number]["section"] {
  if (pathname.includes("/dependencies")) return "dependencies";
  if (pathname.includes("/simulator")) return "simulator";
  if (pathname.includes("/reports")) return "reports";
  return "dashboard";
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const release = releaseFromPath(pathname);
  const current = activeSection(pathname);

  return (
    <div className="flex min-h-screen bg-[var(--tpm-bg)] text-[var(--tpm-ink)]">
      <aside className="sticky top-0 flex h-screen w-[4.5rem] flex-col items-center border-r border-[var(--tpm-line)] bg-[var(--tpm-sidebar)] py-4 lg:w-44 lg:items-stretch lg:px-3">
        <Link
          href={release ? `/releases/${release}` : "/"}
          className="mb-8 px-1 text-center text-xs font-semibold tracking-tight lg:text-left lg:text-sm"
        >
          TPM
          <span className="mt-0.5 block text-[10px] font-normal text-[var(--tpm-muted)] lg:inline lg:before:content-['_']">
            Intelligence
          </span>
        </Link>
        <nav className="flex flex-1 flex-col gap-1" aria-label="Primary">
          {NAV.map((item) => {
            const href = releaseHref(release, item.section);
            const on = current === item.section;
            return (
              <Link
                key={item.section}
                href={href}
                className={`flex items-center gap-2 rounded-md px-2 py-2 text-xs lg:text-sm ${
                  on
                    ? "bg-[var(--tpm-sidebar-active)] font-medium text-[var(--tpm-accent)]"
                    : "text-[var(--tpm-muted)] hover:bg-white/70"
                }`}
                aria-current={on ? "page" : undefined}
              >
                <span aria-hidden className="w-5 text-center text-base">
                  {item.icon}
                </span>
                <span className="hidden lg:inline">{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <p className="hidden px-2 text-[10px] leading-snug text-[var(--tpm-muted)] lg:block">
          {release ? (
            <>
              Release <span className="font-medium text-[var(--tpm-ink)]">{release}</span>
              <br />
            </>
          ) : null}
          Decision support · public data · not guarantees
        </p>
      </aside>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
