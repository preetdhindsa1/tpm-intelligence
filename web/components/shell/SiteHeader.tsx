"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { commandItems, currentId, destinations, readLastSnapshot, subscribeLast, type LastProgram } from "./model";

const noLast = (): null => null;
const linkCls = "inline-flex min-h-11 items-center border-b-2 px-1 text-sm";

export function SiteHeader({ login, signIn }: { login: string | null; signIn: boolean }) {
  const path = usePathname() ?? "/";
  const front = path === "/";
  const last = useSyncExternalStore(subscribeLast, readLastSnapshot, noLast);
  const [open, setOpen] = useState(false);
  const searchBtn = useRef<HTMLButtonElement>(null);
  const closeSearch = () => { setOpen(false); searchBtn.current?.focus(); };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement;
      const typing = el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || (el instanceof HTMLElement && el.isContentEditable);
      const chord = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k";
      if (chord && (open || !typing)) {
        e.preventDefault();
        if (open) closeSearch();
        else setOpen(true);
      } else if (e.key === "Escape" && open) closeSearch();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  const dest = destinations(path, last);
  const here = currentId(path);
  const cockpit = dest.find((d) => d.id === "cockpit")?.href ?? "/releases";
  return (
    <header className="bg-ink text-white">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-4 px-6">
        <Link href="/" className="inline-flex min-h-11 items-center font-heading font-semibold">Program Intelligence</Link>
        <nav aria-label="Main" className="flex flex-wrap items-center gap-x-3">
          {dest.map((d) => (
            <Link key={d.id} href={d.href} aria-current={here === d.id ? "page" : undefined} className={`${linkCls} ${here === d.id ? "border-white font-medium" : "border-transparent text-slate-200 hover:text-white"}`}>
              {d.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex flex-wrap items-center gap-3">
          {front && !login && signIn && <Link href="/api/auth/signin" prefetch={false} className="inline-flex min-h-11 items-center text-sm text-slate-200">Sign in</Link>}
          {front && <Link href={cockpit} className="inline-flex min-h-11 items-center rounded-md bg-action px-3 text-sm font-medium text-white">Open the live demo</Link>}
          {!front && <button ref={searchBtn} type="button" className="inline-flex min-h-11 items-center gap-2 rounded-md border border-white/20 px-3 text-sm" onClick={() => setOpen(true)}>Search <kbd className="text-xs text-slate-300">⌘K</kbd></button>}
          {login && (
            <span className="inline-flex min-h-11 items-center gap-2 text-sm">
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-white/15" aria-label={`Signed in as ${login}`}>{login.slice(0, 1).toUpperCase()}</span>
              <Link href="/api/auth/signout" prefetch={false} className="text-slate-200 hover:underline">Sign out</Link>
            </span>
          )}
        </div>
      </div>
      {open && <CommandPalette path={path} last={last} onClose={closeSearch} />}
    </header>
  );
}

function CommandPalette({ path, last, onClose }: { path: string; last: LastProgram | null; onClose: () => void }) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const [q, setQ] = useState("");
  const [i, setI] = useState(0);
  const items = useMemo(() => {
    const all = commandItems(path, last);
    const n = q.trim().toLowerCase();
    return n ? all.filter((item) => item.label.toLowerCase().includes(n)) : all;
  }, [path, last, q]);
  useEffect(() => input.current?.focus(), []);
  const go = (href: string) => { onClose(); router.push(href); };
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-24">
      <button type="button" aria-label="Close search" className="absolute inset-0 bg-ink/70" onClick={onClose} />
      <div ref={dialog} role="dialog" aria-modal="true" aria-label="Search" className="relative w-full max-w-lg rounded-lg bg-white text-slate-900 shadow-xl"
        onKeyDown={(e) => {
          if (e.key !== "Tab" || !dialog.current) return;
          const nodes = [...dialog.current.querySelectorAll<HTMLElement>("a, button, input")];
          const first = nodes[0];
          const lastNode = nodes[nodes.length - 1];
          if (e.shiftKey && document.activeElement === first) { e.preventDefault(); lastNode?.focus(); }
          else if (!e.shiftKey && document.activeElement === lastNode) { e.preventDefault(); first?.focus(); }
        }}>
        <input ref={input} value={q} aria-label="Search pages" placeholder="Search pages" className="w-full border-b px-4 py-3 text-sm"
          onChange={(e) => { setQ(e.target.value); setI(0); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setI((n) => Math.min(n + 1, Math.max(items.length - 1, 0))); }
            if (e.key === "ArrowUp") { e.preventDefault(); setI((n) => Math.max(n - 1, 0)); }
            if (e.key === "Enter" && items[i]) go(items[i].href);
          }} />
        <ul className="max-h-80 overflow-auto py-2">
          {items.length === 0 && <li className="px-4 py-3 text-sm text-slate-500">No matches</li>}
          {items.map((entry, n) => (
            <li key={`${entry.href}-${entry.label}`}>
              <a href={entry.href} className={`flex min-h-11 items-center px-4 text-sm ${n === i ? "bg-indigo-50 text-action" : ""}`}
                onMouseEnter={() => setI(n)} onClick={(e) => { e.preventDefault(); go(entry.href); }}>{entry.label}</a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
