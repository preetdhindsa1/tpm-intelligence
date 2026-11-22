import Link from "next/link";
import type { ReactNode } from "react";

const NAV = [
  { href: "/", label: "Dashboard", icon: "▦" },
  { href: "#dependencies", label: "Dependencies", icon: "⧉" },
  { href: "#simulations", label: "Simulations", icon: "◎" },
  { href: "#reports", label: "Reports", icon: "☰" },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-[var(--tpm-bg)] text-[var(--tpm-ink)]">
      <aside className="sticky top-0 flex h-screen w-[4.5rem] flex-col items-center border-r border-[var(--tpm-line)] bg-[var(--tpm-sidebar)] py-4 lg:w-44 lg:items-stretch lg:px-3">
        <Link href="/" className="mb-8 px-1 text-center text-xs font-semibold tracking-tight lg:text-left lg:text-sm">
          TPM
          <span className="mt-0.5 block text-[10px] font-normal text-[var(--tpm-muted)] lg:inline lg:before:content-['_']">
            Intelligence
          </span>
        </Link>
        <nav className="flex flex-1 flex-col gap-1">
          {NAV.map((item, i) => (
            <Link
              key={item.label}
              href={item.href}
              className={`flex items-center gap-2 rounded-md px-2 py-2 text-xs lg:text-sm ${
                i === 0
                  ? "bg-[var(--tpm-sidebar-active)] font-medium text-[var(--tpm-accent)]"
                  : "text-[var(--tpm-muted)] hover:bg-white/70"
              }`}
            >
              <span aria-hidden className="w-5 text-center text-base">
                {item.icon}
              </span>
              <span className="hidden lg:inline">{item.label}</span>
            </Link>
          ))}
        </nav>
        <p className="hidden px-2 text-[10px] leading-snug text-[var(--tpm-muted)] lg:block">
          Decision support · public data · not guarantees
        </p>
      </aside>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
