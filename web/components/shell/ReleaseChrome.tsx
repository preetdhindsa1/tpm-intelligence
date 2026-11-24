"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import type { SwitcherGroup } from "@/components/ReleaseSwitcher";
import { switchPath } from "@/lib/routes";
import { writeLast } from "./model";

export function ReleaseChrome({ groups, project, release, displayName, stage, codeFreeze, releaseAt, asOf }: {
  groups: SwitcherGroup[]; project: string; release: string; displayName: string;
  stage: string; codeFreeze: string; releaseAt: string; asOf: string;
}) {
  const router = useRouter();
  const path = usePathname() ?? "";
  useEffect(() => { writeLast(window.localStorage, { project, release, displayName }); }, [project, release, displayName]);
  const options = groups.flatMap((g) => [...g.releases].reverse().map((name) => ({ value: `${g.slug}/${name}`, label: `${g.displayName} · ${name}` })));
  return (
    <div className="space-y-1">
      <nav aria-label="Program" className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
        <Link href="/portfolio" className="inline-flex min-h-11 items-center text-action hover:underline">Portfolio</Link>
        <span aria-hidden>/</span>
        <select aria-label={`${displayName} · ${release}`} className="min-h-11 rounded-md border bg-white px-2 text-sm font-medium text-slate-800" value={`${project}/${release}`}
          onChange={(e) => { const i = e.target.value.indexOf("/"); router.push(switchPath(path, e.target.value.slice(0, i), e.target.value.slice(i + 1))); }}>
          {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </nav>
      <p className="text-sm text-slate-600">{stage} · Code Freeze {codeFreeze} · release {releaseAt} · data as of {asOf}</p>
    </div>
  );
}
