import { featureLabel } from "@/lib/vocab";
import { releaseFromParams } from "@/lib/release-page";
import { releasePath } from "@/lib/routes";
import Link from "next/link";
import { FlagList } from "@/components/Flags";
import { LiveRefresh } from "@/components/LiveRefresh";
import { OddsCell } from "@/components/Odds";
import { RiskNotePanel } from "@/components/RiskNote";
import { Timeline } from "@/components/Timeline";
import { api } from "@/lib/api";
import { dateOf, mergeRangeLabel, relDay } from "@/lib/delay";
import { formatUtc } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function FeaturePage({ params }: { params: Promise<{ project: string; name: string; number: string }> }) {
  const release = await releaseFromParams(params);
  const { number } = await params;
  const name = release.name;
  const project = release.project;
  const f = await api.feature(name, Number(number));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link href={releasePath(project, name)} className="text-sm text-indigo-700 hover:underline">← {name} release health</Link>
          <h1 className="text-2xl font-semibold">
            <a className="hover:underline" href={f.url ?? "#"}>{featureLabel(f)}</a> {f.title}
          </h1>
          <p className="text-sm text-slate-600">
            {f.in_release ? "In the release" : "Removed from the release"} · {f.tracked ? "tracked" : "not tracked"} ·
            stage {f.stage ?? "unknown"} · {f.teams.join(", ")}
          </p>
        </div>
        <LiveRefresh release={name} />
      </div>

      <RiskNotePanel release={name} number={f.number} />

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="rounded border bg-white p-4">
          <h2 className="mb-2 font-medium">Odds of landing by Code Freeze</h2>
          <OddsCell odds={f.odds} />
          <p className="mt-3 text-xs text-slate-500">If the measured inputs below hold, the odds are likely in this range. Not a guarantee.</p>
        </section>
        <section className="rounded border bg-white p-4 lg:col-span-2">
          <h2 className="mb-2 font-medium">When will its required code merge?</h2>
          <MergeDateText f={f} freeze={release.code_freeze_at} />
        </section>
        <section className="rounded border bg-white p-4 lg:col-span-3">
          <h2 className="mb-2 font-medium">Flags</h2>
          <FlagList flags={f.flags} />
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="rounded border bg-white p-4">
          <h2 className="mb-3 font-medium">Timeline</h2>
          <Timeline entries={f.timeline} />
        </section>
        <section className="space-y-4 lg:col-span-2">
          <div className="rounded border bg-white p-4">
            <h2 className="mb-2 font-medium">Linked pull requests (verified)</h2>
            <table className="min-w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500">
                <tr><th className="py-1">PR</th><th>State</th><th>Opened</th><th>Merged</th><th>Review rounds</th><th>Code Freeze</th></tr>
              </thead>
              <tbody className="divide-y">
                {f.pull_requests.map((p) => (
                  <tr key={p.key} className="align-top">
                    <td className="py-1 pr-2">
                      <a className="text-indigo-700 hover:underline" href={p.url}>#{p.key.split("#")[1]}</a>
                      {p.is_main ? <span className="ml-1 rounded bg-indigo-100 px-1 text-[10px] text-indigo-800">main</span> : null}
                      <div className="text-xs text-slate-500">{p.title}</div>
                    </td>
                    <td className="text-xs">{p.state}{p.failing_checks ? ` · ${p.failing_checks} failing checks` : ""}</td>
                    <td className="text-xs">{formatUtc(p.created_at)}</td>
                    <td className="text-xs">{p.merged_at ? formatUtc(p.merged_at) : "—"}</td>
                    <td className="text-xs" title={`${p.review_records} review records`}>{p.review_rounds} ({p.review_records} records)</td>
                    <td className="text-xs">{p.freeze_status.replaceAll("_", " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {f.suggested_pull_requests.length ? (
              <p className="mt-2 text-xs text-slate-500">
                Suggested, not counted until confirmed: {f.suggested_pull_requests.map((k) => `#${k.split("#")[1]}`).join(", ")}
              </p>
            ) : null}
          </div>
          <div className="rounded border bg-white p-4">
            <h2 className="mb-2 font-medium">Critical path (unmerged)</h2>
            {f.critical_path.length ? (
              <p className="text-sm">{f.critical_path.map((k) => `#${k.split("#")[1]}`).join(" → ")}</p>
            ) : (
              <p className="text-sm text-slate-500">Nothing left unmerged.</p>
            )}
          </div>
          <details className="rounded border bg-white p-4 text-xs">
            <summary className="cursor-pointer font-medium">Measured inputs behind the odds</summary>
            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(f.assumptions, null, 2)}</pre>
          </details>
        </section>
      </div>
    </div>
  );
}

function MergeDateText({ f, freeze }: { f: Awaited<ReturnType<typeof api.feature>>; freeze: string | null }) {
  const m = f.merge_date;
  if (!m || m.status === "no_freeze_date") return <p className="text-sm text-slate-500">No Code Freeze date, so no merge-date forecast.</p>;
  if (m.status === "done")
    return (
      <p className="text-sm text-slate-700">
        Merged {m.done_day !== null ? `${dateOf(Math.floor(m.done_day), freeze)} (${relDay(Math.floor(m.done_day))})` : ""}: the main PR
        and the PRs it depends on are all in.
      </p>
    );
  const pct = (x: number | null) => (x === null ? "—" : `${Math.round(x * 100)}%`);
  return (
    <div className="space-y-2 text-sm text-slate-700">
      <p>
        {mergeRangeLabel(m.p10, m.p50, m.p90)}
        {m.p50 !== null ? ` (${dateOf(Math.round(m.p50), freeze)})` : ""}.
      </p>
      <p>
        Odds the required code merges {m.by_freeze !== null ? <>by Code Freeze: <strong>{pct(m.by_freeze)}</strong> (raw, before recalibration) · </> : null}
        by release day: <strong>{pct(m.by_release)}</strong>
      </p>
      {!f.merge_date_validation.validated && (
        <p className="text-xs text-amber-900">Not validated: {f.merge_date_validation.reason ?? "merge dates have not passed their backtest"}.</p>
      )}
      <p className="text-xs text-slate-500">Monte Carlo over measured PR merge times from earlier releases. Decision support, not a guarantee.</p>
    </div>
  );
}
