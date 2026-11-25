// Live Cockpit (UX vision p.4). Title, stage and dates are in the release layout's header.
// Every number is from the release API: summary, features, the #6395 timeline, the latest
// executive update and the simulator's stored validation.
import { featureLabel, vocab } from "@/lib/vocab";
import { releaseFromParams } from "@/lib/release-page";
import { releasePath } from "@/lib/routes";
import Link from "next/link";
import { DelayChart } from "@/components/DelayChart";
import { DependencySummary } from "@/components/DependencySummary";
import { FlagChips } from "@/components/Flags";
import { LiveRefresh } from "@/components/LiveRefresh";
import { OddsCell } from "@/components/Odds";
import { OddsPanel } from "@/components/OddsPanel";
import { api, SECTION_TITLES, type ExecUpdate, type Summary } from "@/lib/api";
import { briefToShow, outcomeRows } from "@/lib/dashboard";
import { recordedLabel } from "@/lib/delay";
import { ErrorState } from "@/components/states/States";
import { errorDetail } from "@/lib/errors";
import { LifecycleBar } from "@/components/cockpit/LifecycleBar";
import { TimeMachine } from "@/components/cockpit/TimeMachine";
import { stageOf } from "@/components/shell/model";
import { dayMonth, keyStops, lifecycle, simValidationText, type KeyStop } from "@/lib/cockpit";

export const dynamic = "force-dynamic";

const REPLAY = { project: "kubernetes", release: "v1.38", feature: 6395 };

export default async function ReleasePage({ params }: { params: Promise<{ project: string; name: string }> }) {
  const release = await releaseFromParams(params);
  const name = release.name;
  const project = release.project;
  let loaded: Awaited<ReturnType<typeof loadCockpit>>;
  try {
    loaded = await loadCockpit(name);
  } catch (e) {
    return <ErrorState title="Live Cockpit could not be loaded" detail={errorDetail(e, "The release API failed")} />;
  }
  const [data, summary, deps, updates, dates, snaps, sim] = loaded;
  const r = data.release;
  const current = data.features.filter((f) => f.in_release);
  const removed = data.features.filter((f) => !f.in_release);
  const before = summary.phase === "before_freeze";
  const stage = stageOf(r, new Date(r.as_of));
  const machine = await timeMachine(project, name);
  const simText = sim && !sim.validated ? simValidationText(sim.validation, r.key) : null;

  return (
    <div className="space-y-5">
      <LifecycleBar steps={lifecycle(r, r.as_of, stage)} />
      <StatTiles summary={summary} />
      {machine && <TimeMachine {...machine} />}

      <div className="grid grid-cols-1 items-stretch gap-5 lg:grid-cols-3">
        <Card eyebrow="Delivery risk" title={before ? "Odds of landing by Code Freeze" : "What happened at Code Freeze"}>
          {before ? (
            <OddsPanel project={project} release={name} rows={data.features} validated={data.validation.validated} />
          ) : (
            <FreezeOutcome summary={summary} />
          )}
        </Card>
        <Card eyebrow="Decide" title="Test a fix before you commit people">
          <p className="text-slate-600">
            Change reviewers, interruptions or the flow of new PRs per {vocab(project).team}, and compare baseline with scenario as ranges.
          </p>
          {sim && !sim.validated && (
            <p className="mt-4 rounded-lg bg-warning-bg px-4 py-3 text-sm text-warning">
              Simulator is <strong>not validated</strong> yet{simText ? `: ${simText}` : "."} Shown as decision support only.
            </p>
          )}
          {!sim && <p className="mt-4 text-sm text-slate-500">No simulator for this release yet.</p>}
          <Link href={releasePath(project, name, "/simulate")} className="mt-4 inline-flex min-h-11 items-center font-semibold text-action hover:underline">
            Open the Decision Studio →
          </Link>
        </Card>
        <Card eyebrow="Verified executive brief" title="Drafted by AI, every line checked">
          <Brief update={briefToShow(updates)} href={releasePath(project, name, "/update")} />
        </Card>
      </div>

      <details className="group rounded-2xl border border-slate-200 bg-white">
        <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between px-6 text-sm font-semibold text-slate-800">
          <span>More detail: merge dates, dependencies and every feature ({current.length} in, {removed.length} removed)</span>
          <span aria-hidden className="text-slate-400 group-open:rotate-180">▾</span>
        </summary>
        <div className="space-y-6 border-t border-slate-100 px-6 py-6">
          <div className="flex justify-end"><LiveRefresh release={name} /></div>
          {!data.validation.validated && before && (
            <p className="rounded-lg bg-warning-bg p-3 text-sm text-warning">
              <strong>Odds are not validated.</strong> {data.validation.reason}. Flags and dates are computed facts and are not affected.
            </p>
          )}
          {dates && (
            <section>
              <h3 className="font-heading font-semibold">When will the remaining code merge?</h3>
              <p className="mb-3 text-xs text-slate-500">Features whose main PR has merged, by day: actual so far, then a Monte Carlo forecast.</p>
              <DelayChart m={dates} recorded={snaps ? recordedLabel(snaps.runs, snaps.current_model_version) : undefined} />
            </section>
          )}
          <section>
            <h3 className="font-heading font-semibold">Feature dependencies</h3>
            <p className="mb-3 text-xs text-slate-500">Features tied by shared PRs or a stated &quot;depends on&quot;.</p>
            <div className="h-[420px]"><DependencySummary project={project} release={name} data={deps} /></div>
          </section>
          <FeatureTable title={`In the release (${current.length})`} rows={current} project={project} release={name} />
          {removed.length ? <FeatureTable title={`Removed from the release (${removed.length})`} rows={removed} project={project} release={name} /> : null}
        </div>
      </details>
    </div>
  );
}

function Card({ eyebrow, title, children }: { eyebrow: string; title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col rounded-2xl border border-slate-200 bg-white p-6">
      <p className="text-xs font-medium uppercase tracking-wider text-slate-500">{eyebrow}</p>
      <h2 className="mt-1.5 font-heading text-xl font-semibold">{title}</h2>
      <div className="mt-4 flex-1">{children}</div>
    </section>
  );
}

function StatTiles({ summary: s }: { summary: Summary }) {
  const readded = s.outcomes.readded_after_freeze ?? 0;
  const tiles: { label: string; value: string; note: string; tone: string }[] = [
    { label: "Features in the release", value: `${s.features_in_release}`, note: `${s.features_ever} were in it at some point`, tone: "text-slate-900" },
    { label: "Landed cleanly", value: s.landed === null ? "—" : `${s.landed}`, note: s.landed === null ? "known 3 days after Code Freeze" : "never removed at the freeze", tone: "text-healthy" },
    { label: "Removed at Code Freeze", value: `${s.removed_at_freeze}`, note: readded ? `${readded} re-added since` : "none re-added", tone: "text-critical" },
    { label: "Critical flag", value: `${s.critical_features}`, note: "in the release now", tone: "text-warning" },
    { label: "Unlinked open PRs", value: s.unlinked_open_prs.toLocaleString("en-US"), note: "same reviewers, no feature", tone: "text-slate-900" },
  ];
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-2xl border border-slate-200 bg-white px-5 py-4">
          <p className="text-sm text-slate-600">{t.label}</p>
          <p className={`mt-1 font-heading text-4xl font-bold ${t.tone}`}>{t.value}</p>
          <p className="mt-1 text-sm text-slate-500">{t.note}</p>
        </div>
      ))}
    </div>
  );
}

// Segment colors differ in lightness as well as hue, and every segment is named in the legend.
const SEGMENT: Record<string, string> = {
  landed: "#166534",
  landed_prs_after_freeze: "#4ADE80",
  landed_main_pr_open: "#FBBF24",
  readded_after_freeze: "#A5B4FC",
  removed_after_freeze: "#F87171",
  removed_at_freeze: "#B91C1C",
  removed_before_freeze: "#CBD5E1",
};

function FreezeOutcome({ summary }: { summary: Summary }) {
  const rows = outcomeRows(summary).filter((r) => r.count > 0 && SEGMENT[r.outcome]);
  const total = rows.reduce((n, r) => n + r.count, 0);
  if (total === 0) return <p className="text-sm text-slate-500">Outcomes are known 3 days after Code Freeze.</p>;
  const text = rows.map((r) => `${r.label} ${r.count}`).join(", ");
  return (
    <div>
      <div className="flex h-4 gap-0.5 overflow-hidden rounded" role="img" aria-label={`${total} features: ${text}`}>
        {rows.map((r) => (
          <span key={r.outcome} title={`${r.label}: ${r.count}`} style={{ width: `${(r.count / total) * 100}%`, background: SEGMENT[r.outcome] }} />
        ))}
      </div>
      <ul className="mt-4 space-y-1.5 text-sm">
        {rows.map((r) => (
          <li key={r.outcome} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-slate-700">
              <span aria-hidden className="h-3 w-3 rounded-sm" style={{ background: SEGMENT[r.outcome] }} />
              {r.label}
            </span>
            <span className="font-semibold text-slate-900">{r.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Brief({ update, href }: { update: ExecUpdate | null; href: string }) {
  if (!update) {
    return (
      <p className="text-sm text-slate-600">
        No update drafted yet. <Link href={href} className="font-semibold text-action hover:underline">Draft one →</Link>
      </p>
    );
  }
  const claims = Object.keys(SECTION_TITLES).flatMap((k) => update.sections[k] ?? []);
  const approved = update.status === "approved";
  const when = update.decided_at ? `${dayMonth(update.decided_at)}, ${new Date(update.decided_at).toISOString().slice(11, 16)} UTC` : "";
  return (
    <div>
      {approved ? (
        <p className="inline-block rounded-lg bg-healthy-bg px-3 py-1 text-sm font-medium text-healthy">Approved by the TPM{when ? ` · ${when}` : ""}</p>
      ) : (
        <p className="inline-block rounded-lg bg-warning-bg px-3 py-1 text-sm font-medium text-warning">Draft, awaiting TPM approval</p>
      )}
      {update.stale && <p className="mt-2 text-xs text-slate-500">Facts changed since this was drafted.</p>}
      <ul className="mt-3 list-disc space-y-1.5 pl-5 text-slate-700">
        {claims.slice(0, 3).map((c) => <li key={c.text}>{c.text}</li>)}
      </ul>
      <p className="mt-3 text-xs text-slate-500">
        Every line checked against the data. {update.claims_removed} claim{update.claims_removed === 1 ? "" : "s"} removed.{" "}
        <Link href={href} className="font-semibold text-action hover:underline">Open the update →</Link>
      </p>
    </div>
  );
}

function FeatureTable({ title, rows, project, release }: { title: string; rows: Awaited<ReturnType<typeof api.features>>["features"]; project: string; release: string }) {
  return (
    <section>
      <h3 className="mb-2 font-heading font-semibold">{title}</h3>
      <div className="overflow-x-auto rounded-lg border">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">Feature</th>
              <th className="px-3 py-2">{vocab(project).teams}</th>
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
                  <Link className="font-medium text-action hover:underline" href={releasePath(project, release, `/features/${f.number}`)}>
                    {featureLabel(f)}
                  </Link>{" "}
                  {f.title}
                  {vocab(project).tracking && !f.tracked && f.in_release ? <span className="ml-1 text-xs text-slate-500">(not tracked)</span> : null}
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

function loadCockpit(name: string) {
  return Promise.all([
    api.features(name),
    api.summary(name),
    api.dependencies(name),
    api.updates(name).catch(() => []),
    api.mergeDates(name).catch(() => null),
    api.snapshots(name).catch(() => null),
    api.simulator(name).catch(() => null),
  ]);
}

async function timeMachine(project: string, release: string): Promise<{ feature: number; title: string; context: string; stops: KeyStop[]; error: string | null } | null> {
  if (project.toLowerCase() !== REPLAY.project || release !== REPLAY.release) return null;
  try {
    const f = await api.feature(release, REPLAY.feature);
    const teams = f.teams.map((t) => t.replace(/^sig\//, "SIG ").replace(/\b\w/g, (c) => c.toUpperCase()));
    const context = [teams.join(" + "), f.stage].filter(Boolean).join(" · ");
    return { feature: REPLAY.feature, title: f.title, context, stops: keyStops(f.timeline, f.pull_requests, f.teams), error: null };
  } catch (e) {
    return { feature: REPLAY.feature, title: "", context: "", stops: [], error: errorDetail(e, `Feature #${REPLAY.feature} could not be loaded`) };
  }
}
