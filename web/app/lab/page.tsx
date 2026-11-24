import { LabPicker } from "@/components/LabPicker";
import { api, type LabReport } from "@/lib/api";
import { groupByProject } from "@/lib/routes";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

const OWN = "tpm-intelligence";

export default async function LabPage({
  searchParams,
}: {
  searchParams: Promise<{ project?: string; release?: string; cap?: string; lines?: string }>;
}) {
  const query = await searchParams;
  const groups = groupByProject(await api.releases()).map((g) => ({
    slug: g.slug,
    displayName: g.displayName,
    releases: g.releases.map((r) => r.name),
  }));
  const project = (query.project ?? OWN).toLowerCase();
  const group = groups.find((g) => g.slug === project);
  if (!group) notFound();
  const newest = [...group.releases].reverse()[0];
  const release = project === OWN ? null : (query.release ?? newest ?? null);
  if (project !== OWN && !release) notFound();
  const cap = clamp(query.cap, 2, 1, 20);
  const lines = clamp(query.lines, 400, 1, 5000);
  const lab = await api.lab(project, release ?? undefined, cap, lines);
  const medianReview = median(lab.time_to_first_review_hours);
  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold">Multi-Agent Development and PR Lab</h1>
        <p className="max-w-3xl text-sm text-slate-600">
          Counts come from pull requests already stored. Lanes are tools on this repository, not people. Under 20
          merges the sample is small. This is not a forecast.
        </p>
        <LabPicker groups={groups} project={project} release={release} />
      </div>
      {!lab.lanes_configured && (
        <p className="rounded-lg border bg-white p-4 text-sm text-slate-700">
          Agent lanes are only configured for Program Intelligence Platform. Opened, merged, still open, and the
          approval rate below are for this release.
        </p>
      )}
      {lab.small_sample && (
        <p className="text-sm text-slate-600">
          Small sample: {lab.n_merged} merged, under 20. The counts are shown. What-if numbers stay blank.
        </p>
      )}
      {lab.n_pull_requests === 0 ? (
        <p className="rounded-lg border bg-white p-4 text-sm text-slate-700">No pull requests in this window.</p>
      ) : (
        <>
          <section className="rounded-lg border bg-white p-4 text-sm">
            <h2 className="font-medium">Pull requests by lane</h2>
            <table className="mt-2 w-full text-left">
              <thead className="text-slate-500">
                <tr>
                  <th className="py-1">Lane</th>
                  <th>Opened</th>
                  <th>Merged</th>
                  <th>Still open</th>
                </tr>
              </thead>
              <tbody>
                {lab.buckets.map((row) => (
                  <tr key={row.lane} className="border-t">
                    <td className="py-1">{row.lane}</td>
                    <td>{row.opened}</td>
                    <td>{row.merged}</td>
                    <td>{row.still_open}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Stat label="Opened" value={String(lab.n_pull_requests)} />
            <Stat label="Merged" value={String(lab.n_merged)} />
            <Stat label="Still open" value={String(lab.n_open)} />
            <Stat label="Approval rate" value={rate(lab)} />
            <Stat label="Approved merges" value={String(lab.approved_merged)} />
            <Stat
              label="Median hours open to merge"
              value={lab.median_hours_to_merge === null ? "—" : lab.median_hours_to_merge.toFixed(1)}
            />
            <Stat label="Waiting for a first review" value={String(lab.still_waiting)} />
            <Stat label="Median hours to first review" value={medianReview === null ? "—" : medianReview.toFixed(1)} />
            <Stat
              label="Median review rounds"
              value={lab.review_rounds_median === null ? "—" : String(lab.review_rounds_median)}
            />
            <Stat label="Rework" value={String(lab.rework)} />
            <Stat label="CI failures" value={String(lab.ci_failures)} />
            <Stat label="Collisions" value={String(lab.collisions.length)} />
            {lab.lanes_configured && <Stat label="Open agent PRs, peak" value={String(lab.cap.observed_max_open)} />}
          </section>
          <section className="rounded-lg border bg-white p-4 text-sm">
            <h2 className="font-medium">Collisions</h2>
            {lab.collisions.length === 0 ? (
              <p className="mt-2 text-slate-600">None in this window.</p>
            ) : (
              <ul className="mt-2 space-y-1">
                {lab.collisions.map((c) => (
                  <li key={`${c.kind}-${c.pull_requests.join()}`}>
                    {c.kind === "merge_conflict" ? "Conflict with main" : "Shared files"}: {c.pull_requests.join(", ")}
                    {c.paths.length ? ` (${c.paths.join(", ")})` : ""}
                    {c.truncated ? " — file list truncated" : ""}
                  </li>
                ))}
              </ul>
            )}
          </section>
          {lab.lanes_configured && (
            <section className="rounded-lg border bg-white p-4 text-sm">
              <h2 className="font-medium">What-if</h2>
              <form className="mt-2 flex flex-wrap items-end gap-3" method="get">
                <input type="hidden" name="project" value={project} />
                {release && <input type="hidden" name="release" value={release} />}
                <label>
                  Cap open agent pull requests
                  <input className="mt-1 block w-24 rounded border px-2 py-1" name="cap" type="number" min={1} max={20} defaultValue={cap} />
                </label>
                <label>
                  Line cap
                  <input className="mt-1 block w-24 rounded border px-2 py-1" name="lines" type="number" min={1} max={5000} defaultValue={lines} />
                </label>
                <button className="rounded bg-indigo-600 px-3 py-1.5 text-white" type="submit">
                  Replay
                </button>
              </form>
              {lab.cap.comparable ? (
                <p className="mt-3 text-slate-700">
                  Peak open agent pull requests {lab.cap.observed_max_open} → {lab.cap.scenario_max_open}. Held {lab.cap.held}.
                  Pull requests over {lines} lines: {lab.size.over_cap}, which would add {lab.size.extra_pull_requests}.
                </p>
              ) : (
                <p className="mt-3 text-slate-700">
                  Not enough merged pull requests to compare a what-if. Observed peak open agent pull requests:{" "}
                  {lab.cap.observed_max_open}. Pull requests over {lines} lines: {lab.size.over_cap}.
                </p>
              )}
              <p className="mt-2 text-slate-600">{lab.first_pass.assumption}</p>
              <p className="text-slate-600">
                Observed median hours to first review:{" "}
                {lab.first_pass.observed_median_hours === null ? "—" : lab.first_pass.observed_median_hours.toFixed(1)} (n=
                {lab.first_pass.n}).
              </p>
            </section>
          )}
          <section className="rounded-lg border bg-white p-4 text-sm">
            <h2 className="font-medium">Opened by week</h2>
            <table className="mt-2 w-full text-left">
              <thead className="text-slate-500">
                <tr>
                  <th className="py-1">Week</th>
                  <th>Lane</th>
                  <th>Opened</th>
                </tr>
              </thead>
              <tbody>
                {lab.arrivals.map((row) => (
                  <tr key={`${row.week}-${row.lane}`} className="border-t">
                    <td className="py-1">{row.week}</td>
                    <td>{row.lane}</td>
                    <td>{row.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}

function rate(lab: LabReport): string {
  if (lab.approval_rate === null) return "—";
  return `${Math.round(lab.approval_rate * 100)}%`;
}

function clamp(raw: string | undefined, fallback: number, min: number, max: number): number {
  const n = Number(raw ?? fallback);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, Math.round(n)));
}

function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  );
}
