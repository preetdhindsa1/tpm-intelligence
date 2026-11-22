// Release health across projects (ADR-0014): one card for each project's current
// release, then every known release. Each card shows only that release's own facts;
// numbers are never added up across projects (their scopes and definitions differ).
import Link from "next/link";
import { Suspense } from "react";
import { api, type Release } from "@/lib/api";
import { formatUtc } from "@/lib/format";
import { currentRelease, groupByProject, nextMilestone, releasePath } from "@/lib/routes";

export const dynamic = "force-dynamic";

const DAY = 86_400_000;

export default async function Home() {
  const releases = await api.releases();
  const groups = groupByProject(releases);
  const asOf = releases[0] ? new Date(releases[0].as_of) : new Date();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Release health</h1>
        <p className="text-sm text-slate-600">
          Every connected project and its releases. Data as of {formatUtc(asOf.toISOString())}. Projects are added by a team
          connector file; only projects with collected data appear here.
        </p>
      </div>
      {groups.length === 0 && <p className="text-sm text-slate-500">No release data collected yet.</p>}
      {groups.map((g) => {
        const cur = currentRelease(g.releases, asOf);
        return (
          <section key={g.slug} className="space-y-3">
            <h2 className="text-lg font-semibold text-slate-800">{g.displayName}</h2>
            {cur && <CurrentCard release={cur} asOf={asOf} />}
            <ReleaseTable releases={g.releases} current={cur?.name} asOf={asOf} />
          </section>
        );
      })}
    </div>
  );
}

function CurrentCard({ release: r, asOf }: { release: Release; asOf: Date }) {
  const next = nextMilestone(r, asOf);
  const days = next ? Math.ceil((new Date(next.at).getTime() - asOf.getTime()) / DAY) : null;
  return (
    <Link
      href={releasePath(r.project, r.name)}
      className="block rounded-lg border bg-white p-4 shadow-sm transition hover:border-indigo-300 hover:shadow"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-xl font-semibold text-slate-900">
          {r.display_name || r.project} {r.name}
        </p>
        <p className="text-sm text-slate-600">
          {next
            ? `${next.label} in ${days} day${days === 1 ? "" : "s"} · ${formatUtc(next.at)}`
            : `Released ${r.release_at ? formatUtc(r.release_at) : ""}`}
        </p>
      </div>
      <Suspense fallback={<p className="mt-3 text-sm text-slate-500">Loading release facts…</p>}>
        <CardStats release={r} />
      </Suspense>
      <p className="mt-3 text-sm font-medium text-indigo-700">Open release dashboard →</p>
    </Link>
  );
}

async function CardStats({ release: r }: { release: Release }) {
  const s = await api.summary(r.name).catch(() => null);
  if (!s) return <p className="mt-3 text-sm text-slate-500">Release facts are unavailable right now.</p>;
  const stats: [string, string][] = [
    ["Features in the release", `${s.features_in_release}`],
    ["Landed", s.landed === null ? "—" : `${s.landed}`],
    ["Removed at Code Freeze", `${s.removed_at_freeze}`],
    ["With a critical flag", `${s.critical_features}`],
    ["Open linked PRs", `${s.open_linked_prs}`],
  ];
  return (
    <dl className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-5">
      {stats.map(([label, value]) => (
        <div key={label} className="rounded-md bg-slate-50 px-3 py-2">
          <dt className="text-xs text-slate-500">{label}</dt>
          <dd className="text-xl font-semibold text-slate-900">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function ReleaseTable({ releases, current, asOf }: { releases: Release[]; current?: string; asOf: Date }) {
  return (
    <div className="overflow-x-auto rounded border bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-100 text-left text-xs uppercase text-slate-600">
          <tr>
            <th className="px-3 py-2">Release</th>
            <th className="px-3 py-2">Code Freeze</th>
            <th className="px-3 py-2">Release day</th>
            <th className="px-3 py-2">Features in the release</th>
            <th className="px-3 py-2">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {[...releases].reverse().map((r) => (
            <tr key={r.key}>
              <td className="px-3 py-2">
                <Link href={releasePath(r.project, r.name)} className="font-medium text-indigo-700 hover:underline">
                  {r.name}
                </Link>
              </td>
              <td className="px-3 py-2 text-xs">{r.code_freeze_at ? formatUtc(r.code_freeze_at) : "—"}</td>
              <td className="px-3 py-2 text-xs">{r.release_at ? formatUtc(r.release_at) : "—"}</td>
              <td className="px-3 py-2 text-xs">
                {r.features_in_release} ({r.features_ever_in_release} ever)
              </td>
              <td className="px-3 py-2 text-xs">
                {r.name === current ? "current" : r.release_at && new Date(r.release_at) <= asOf ? "released" : "upcoming"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
