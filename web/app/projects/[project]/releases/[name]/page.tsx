import { releaseFromParams } from "@/lib/release-page";
import { releasePath } from "@/lib/routes";
import Link from "next/link";
import { DelayChart } from "@/components/DelayChart";
import { DependencySummary } from "@/components/DependencySummary";
import { ExecBrief } from "@/components/ExecBrief";
import { FlagChips } from "@/components/Flags";
import { LiveRefresh } from "@/components/LiveRefresh";
import { OddsCell } from "@/components/Odds";
import { OddsPanel } from "@/components/OddsPanel";
import { OutcomeChart } from "@/components/OutcomeChart";
import { api, type Summary } from "@/lib/api";
import { briefToShow } from "@/lib/dashboard";
import { recordedLabel } from "@/lib/delay";
import { formatUtc } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function ReleasePage({ params }: { params: Promise<{ project: string; name: string }> }) {
  const release = await releaseFromParams(params);
  const name = release.name;
  const project = release.project;
  const [data, summary, deps, updates, dates, snaps] = await Promise.all([
    api.features(name),
    api.summary(name),
    api.dependencies(name),
    api.updates(name).catch(() => []),
    api.mergeDates(name).catch(() => null),
    api.snapshots(name).catch(() => null),
  ]);
  const r = data.release;
  const current = data.features.filter((f) => f.in_release);
  const removed = data.features.filter((f) => !f.in_release);
  const before = summary.phase === "before_freeze";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">
            {r.display_name || r.project || "Team"} {r.name} release health
          </h1>
          <p className="text-sm text-slate-600">
            Code Freeze {r.code_freeze_at ? formatUtc(r.code_freeze_at) : "unknown"} · release{" "}
            {r.release_at ? formatUtc(r.release_at) : "unknown"} · data as of {formatUtc(r.as_of)}
          </p>
        </div>
        <LiveRefresh release={name} />
      </div>

      <StatTiles summary={summary} />

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <Panel title="Feature dependencies" subtitle="Features tied by shared PRs or a stated &quot;depends on&quot;">
          <div className="h-[480px]">
            <DependencySummary project={project} release={name} data={deps} />
          </div>
        </Panel>
        <Panel
          title={before ? "Odds of landing by Code Freeze" : "What happened at Code Freeze"}
          subtitle={
            before
              ? "Monte Carlo forecast, ranges over runs"
              : `Facts: in the release 3 days after Code Freeze, and what the flags show. ${summary.features_ever} features.`
          }
        >
          {before ? (
            <OddsPanel project={project} release={name} rows={data.features} validated={data.validation.validated} />
          ) : (
            <div className="h-[440px]">
              <OutcomeChart summary={summary} />
            </div>
          )}
        </Panel>
        <Panel title="Verified executive brief" subtitle="AI-drafted, every line fact-checked, TPM-approved">
          <div className="h-[480px] overflow-y-auto pr-1">
            <ExecBrief project={project} release={name} update={briefToShow(updates)} />
          </div>
        </Panel>
      </div>

      {dates && (
        <Panel
          title="When will the remaining code merge?"
          subtitle="Features whose main PR (and the PRs it depends on) has merged, by day: actual so far, then a Monte Carlo forecast"
        >
          <DelayChart m={dates} recorded={snaps ? recordedLabel(snaps.runs, snaps.current_model_version) : undefined} />
        </Panel>
      )}

      {!data.validation.validated && before ? (
        <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <strong>Odds are not validated.</strong> {data.validation.reason}. Read them next to the base rate shown in each
          cell. Flags and dates are computed facts and are not affected.
        </div>
      ) : null}

      <FeatureTable title={`In the release (${current.length})`} rows={current} project={project} release={name} />
      {removed.length ? <FeatureTable title={`Removed from the release (${removed.length})`} rows={removed} project={project} release={name} /> : null}
    </div>
  );
}

function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border bg-white p-4 shadow-sm">
      <h2 className="font-semibold text-slate-800">{title}</h2>
      <p className="mb-3 text-xs text-slate-500">{subtitle}</p>
      {children}
    </section>
  );
}

function StatTiles({ summary: s }: { summary: Summary }) {
  const tiles: { label: string; value: string; note?: string }[] = [
    { label: "Features in the release", value: `${s.features_in_release}`, note: `${s.features_ever} ever` },
    { label: "Landed", value: s.landed === null ? "—" : `${s.landed}`, note: s.landed === null ? "known 3 days after freeze" : "never removed at freeze" },
    {
      label: "Removed at Code Freeze",
      value: `${s.removed_at_freeze}`,
      note: s.outcomes.readded_after_freeze ? `${s.outcomes.readded_after_freeze} since re-added` : undefined,
    },
    { label: "With a critical flag", value: `${s.critical_features}`, note: "in the release now" },
    { label: "Open linked PRs", value: `${s.open_linked_prs}`, note: `${s.unlinked_open_prs} open PRs not linked to a feature` },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-lg border bg-white px-4 py-3 shadow-sm">
          <p className="text-xs text-slate-500">{t.label}</p>
          <p className="text-2xl font-semibold text-slate-900">{t.value}</p>
          {t.note && <p className="text-xs text-slate-500">{t.note}</p>}
        </div>
      ))}
    </div>
  );
}

function FeatureTable({ title, rows, project, release }: { title: string; rows: Awaited<ReturnType<typeof api.features>>["features"]; project: string; release: string }) {
  return (
    <section>
      <h2 className="mb-2 text-lg font-medium">{title}</h2>
      <div className="overflow-x-auto rounded border bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-100 text-left text-xs uppercase text-slate-600">
            <tr>
              <th className="px-3 py-2">Feature</th>
              <th className="px-3 py-2">SIGs</th>
              <th className="px-3 py-2">Stage</th>
              <th className="px-3 py-2">Odds by Code Freeze</th>
              <th className="px-3 py-2">Flags</th>
              <th className="px-3 py-2">Linked PRs</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((f) => (
              <tr key={f.key} className="align-top">
                <td className="px-3 py-2">
                  <Link className="font-medium text-indigo-700 hover:underline" href={releasePath(project, release, `/features/${f.number}`)}>
                    #{f.number}
                  </Link>{" "}
                  {f.title}
                  {!f.tracked && f.in_release ? <span className="ml-1 text-xs text-slate-500">(not tracked)</span> : null}
                </td>
                <td className="px-3 py-2 text-xs text-slate-600">{f.teams.map((t) => t.replace("sig/", "")).join(", ")}</td>
                <td className="px-3 py-2 text-xs">{f.stage ?? "—"}</td>
                <td className="px-3 py-2"><OddsCell odds={f.odds} /></td>
                <td className="px-3 py-2"><FlagChips flags={f.flags} /></td>
                <td className="px-3 py-2 text-xs">
                  {f.prs_merged}/{f.prs_total} merged
                  {f.prs_open ? ` · ${f.prs_open} open` : ""}
                  {f.suggested_prs ? <div className="text-slate-500">{f.suggested_prs} suggested (unconfirmed)</div> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
