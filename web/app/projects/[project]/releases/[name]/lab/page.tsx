import { releaseFromParams } from "@/lib/release-page";
import { api } from "@/lib/api";
import { releasePath } from "@/lib/routes";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function LabPage({
  params,
  searchParams,
}: {
  params: Promise<{ project: string; name: string }>;
  searchParams: Promise<{ cap?: string; lines?: string }>;
}) {
  const release = await releaseFromParams(params);
  const query = await searchParams;
  const cap = clamp(query.cap, 2, 1, 20);
  const lines = clamp(query.lines, 400, 1, 5000);
  const lab = await api.lab(release.name, cap, lines);
  const hours = lab.time_to_first_review_hours;
  const medianHours = hours.length ? median(hours) : null;
  return (
    <div className="space-y-6">
      <div>
        <Link href={releasePath(release.project, release.name)} className="text-sm text-indigo-700 hover:underline">
          ← {release.name} release health
        </Link>
        <h1 className="text-2xl font-semibold">Development lab</h1>
        <p className="mt-1 text-sm text-slate-600">
          Case study of this repository. The lanes are tools allowed here, not people. Counts come from pull requests
          already opened. {lab.small_sample ? `Small sample: ${lab.n_merged} merged, under 20.` : `${lab.n_merged} merged.`}{" "}
          Not a forecast.
        </p>
      </div>
      {lab.n_pull_requests === 0 ? (
        <p className="rounded-lg border bg-white p-4 text-sm text-slate-700">
          No pull requests yet. Protecting main is what creates this queue.
        </p>
      ) : (
        <>
          <section className="rounded-lg border bg-white p-4 text-sm">
            <h2 className="font-medium">Pull requests by lane</h2>
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
          <section className="grid gap-4 sm:grid-cols-2">
            <Stat label="Waiting for a first review" value={String(lab.still_waiting)} />
            <Stat label="Median hours to first review" value={medianHours === null ? "—" : medianHours.toFixed(1)} />
            <Stat label="Median review rounds" value={lab.review_rounds_median === null ? "—" : String(lab.review_rounds_median)} />
            <Stat label="Rework" value={String(lab.rework)} />
            <Stat label="CI failures" value={String(lab.ci_failures)} />
            <Stat label="Open agent PRs, peak" value={String(lab.cap.observed_max_open)} />
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
          <section className="rounded-lg border bg-white p-4 text-sm">
            <h2 className="font-medium">What-if</h2>
            <form className="mt-2 flex flex-wrap items-end gap-3" method="get">
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
                Peak open agent pull requests {lab.cap.observed_max_open} → {lab.cap.scenario_max_open}. Held {lab.cap.held}. Pull
                requests over {lines} lines: {lab.size.over_cap}, which would add {lab.size.extra_pull_requests}.
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
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-white p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-xl font-semibold">{value}</p>
    </div>
  );
}

function clamp(raw: string | undefined, fallback: number, min: number, max: number): number {
  const n = Number(raw ?? fallback);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, Math.round(n)));
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}
