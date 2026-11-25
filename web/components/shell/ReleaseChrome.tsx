"use client";

// Program header for every release page (UX vision p.4–5): switcher breadcrumb, then on
// Live Cockpit and Decision Studio the screen title, the stage and date line, and actions.
// Dates are the release's own; this file only words them.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import type { SwitcherGroup } from "@/components/ReleaseSwitcher";
import { dayMonth, daysFrom } from "@/lib/cockpit";
import { releasePath, switchPath } from "@/lib/routes";
import { cockpitSection, writeLast } from "./model";

const asOfLabel = (iso: string) => `${dayMonth(iso)}, ${new Date(iso).toISOString().slice(11, 16)} UTC`;

/** "Code Freeze passed 17 Nov" / "Code Freeze 17 Nov · in 9 days". */
export function freezeText(freeze: string | null, asOf: string): string | null {
  if (!freeze) return null;
  const d = daysFrom(asOf, freeze);
  return d <= 0 ? `Code Freeze passed ${dayMonth(freeze)}` : `Code Freeze ${dayMonth(freeze)} · in ${d} day${d === 1 ? "" : "s"}`;
}

/** "Release 16 Dec · in 21 days" / "Released 16 Dec". */
export function releaseText(release: string | null, asOf: string): string | null {
  if (!release) return null;
  const d = daysFrom(asOf, release);
  return d <= 0 ? `Released ${dayMonth(release)}` : `Release ${dayMonth(release)} · in ${d} day${d === 1 ? "" : "s"}`;
}

export function ReleaseChrome({ groups, project, release, displayName, stage, codeFreezeAt, releaseAt, asOf }: {
  groups: SwitcherGroup[]; project: string; release: string; displayName: string;
  stage: string; codeFreezeAt: string | null; releaseAt: string | null; asOf: string;
}) {
  const router = useRouter();
  const path = usePathname() ?? "";
  useEffect(() => { writeLast(window.localStorage, { project, release, displayName }); }, [project, release, displayName]);
  const options = groups.flatMap((g) => [...g.releases].reverse().map((name) => ({ value: `${g.slug}/${name}`, label: `${g.displayName} · ${name}` })));
  const section = cockpitSection(path);
  const studio = path.endsWith("/simulate");
  const title = studio ? "Decision Studio" : section === "" && !path.includes("/features/") ? "Live Cockpit" : null;
  const meta = [freezeText(codeFreezeAt, asOf), releaseText(releaseAt, asOf), `Data as of ${asOfLabel(asOf)}`].filter(Boolean) as string[];
  return (
    <div className="space-y-3">
      <nav aria-label="Program" className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
        <Link href="/portfolio" className="inline-flex min-h-11 items-center text-action hover:underline">Portfolio</Link>
        <span aria-hidden>/</span>
        <select aria-label={`${displayName} · ${release}`} className="min-h-11 min-w-0 max-w-full rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-800" value={`${project}/${release}`}
          onChange={(e) => { const i = e.target.value.indexOf("/"); router.push(switchPath(path, e.target.value.slice(0, i), e.target.value.slice(i + 1))); }}>
          {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </nav>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          {title && (
            <h1 className="font-heading text-3xl font-bold tracking-tight md:text-4xl">
              {title} · {displayName.replace(/\s*\(this project\)$/, "")} {release}
            </h1>
          )}
          <p className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-slate-600">
            <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 font-medium text-action">Stage: {stage}</span>
            {meta.map((m) => <span key={m}>{m}</span>)}
          </p>
        </div>
        {title === "Live Cockpit" && (
          <div className="flex flex-wrap gap-3">
            <Link href={releasePath(project, release, "/simulate")} className="inline-flex min-h-11 items-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50">Test a fix</Link>
            <Link href={releasePath(project, release, "/update")} className="inline-flex min-h-11 items-center rounded-lg bg-action px-4 text-sm font-semibold text-white hover:bg-action/90">Review exec update</Link>
          </div>
        )}
        {studio && (
          <a href="#saved" className="inline-flex min-h-11 items-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50">Saved scenarios</a>
        )}
      </div>
    </div>
  );
}
