import { LabPicker } from "@/components/LabPicker";
import { api, type LabReport } from "@/lib/api";
import { groupByProject } from "@/lib/routes";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

const OWN = "tpm-intelligence";

export default async function LabPage({
  searchParams,
}: {
  searchParams: Promise<{ project?: string; release?: string }>;
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
  const lab = await api.lab(project, release ?? undefined);
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
            <Stat label="Median hours to first review" value={medianReview === null ? "—" : medianReview.toFixed(1)} />
            <Stat
              label="Median review rounds"
              value={lab.review_rounds_median === null ? "—" : String(lab.review_rounds_median)}
            />
            <Stat label="Rework" value={String(lab.rework)} />
            <Stat label="CI failures" value={String(lab.ci_failures)} />
            <Stat label="Collisions" value={String(lab.collisions.length)} />
          </section>
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
