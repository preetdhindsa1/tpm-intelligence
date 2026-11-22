"use client";

// Project / release breadcrumb with two linked pickers (ADR-0014). Picking a project
// opens that project's newest release; picking a release keeps the current section
// (Dependencies, Simulations, ...) when that section exists for every release.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { releasePath, switchPath } from "@/lib/routes";

export type SwitcherGroup = { slug: string; displayName: string; releases: string[] };

export function ReleaseSwitcher({ groups, project, release }: { groups: SwitcherGroup[]; project: string; release: string }) {
  const router = useRouter();
  const path = usePathname();
  const current = groups.find((g) => g.slug === project);
  const select = "rounded-md border bg-white px-2 py-1 text-sm font-medium text-slate-800";
  return (
    <nav aria-label="Project and release" className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
      <Link href="/releases" className="text-indigo-700 hover:underline">
        All releases
      </Link>
      <span aria-hidden>/</span>
      <select
        aria-label="Project"
        className={select}
        value={project}
        onChange={(e) => {
          const g = groups.find((x) => x.slug === e.target.value);
          const newest = g?.releases.at(-1);
          if (g && newest) router.push(releasePath(g.slug, newest));
        }}
      >
        {groups.map((g) => (
          <option key={g.slug} value={g.slug}>
            {g.displayName}
          </option>
        ))}
      </select>
      <span aria-hidden>/</span>
      <select
        aria-label="Release"
        className={select}
        value={release}
        onChange={(e) => router.push(switchPath(path, project, e.target.value))}
      >
        {[...(current?.releases ?? [])].reverse().map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>
    </nav>
  );
}
