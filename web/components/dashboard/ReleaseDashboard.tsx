"use client";

import Link from "next/link";
import type { FeatureRow, Release, Validation } from "@/lib/api";
import { formatUtc } from "@/lib/format";
import { LiveRefresh } from "@/components/LiveRefresh";
import { FlagChips } from "@/components/Flags";
import { OddsCell } from "@/components/Odds";
import { DependencyGraph } from "@/components/dashboard/DependencyGraph";
import { MonteCarloPanel } from "@/components/dashboard/MonteCarloPanel";
import { ExecutiveBrief } from "@/components/dashboard/ExecutiveBrief";

export function ReleaseDashboard({
  releaseName,
  release,
  features,
  validation,
}: {
  releaseName: string;
  release: Release;
  features: FeatureRow[];
  validation: Validation;
}) {
  const current = features.filter((f) => f.in_release);
  const removed = features.filter((f) => !f.in_release);
  const label = `${release.display_name || release.project || "Team"} ${release.name}`;

  return (
    <div className="flex h-full min-h-screen flex-col">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-[var(--tpm-line)] bg-white px-5 py-4">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-[var(--tpm-muted)]">Release dashboard</p>
          <h1 className="text-xl font-semibold tracking-tight">{label}</h1>
          <p className="text-sm text-[var(--tpm-muted)]">
            Code Freeze {release.code_freeze_at ? formatUtc(release.code_freeze_at) : "unknown"} ·{" "}
            {release.features_in_release} in release · {release.features_ever_in_release} ever · as of{" "}
            {formatUtc(release.as_of)}
          </p>
        </div>
        <LiveRefresh release={releaseName} />
      </header>

      <div className="grid flex-1 gap-4 p-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(16rem,0.85fr)_minmax(16rem,0.85fr)]">
        <DependencyGraph features={features} releaseLabel={label} />
        <MonteCarloPanel features={features} validation={validation} />
        <ExecutiveBrief release={releaseName} features={features} />
      </div>

      <section id="reports" className="space-y-4 border-t border-[var(--tpm-line)] px-4 pb-8 pt-2">
        <FeatureTable title={`In the release (${current.length})`} rows={current} release={releaseName} />
        {removed.length ? (
          <FeatureTable title={`Removed (${removed.length})`} rows={removed} release={releaseName} />
        ) : null}
        <p id="simulations" className="text-xs text-[var(--tpm-muted)]">
          Simulations: Shadow-Org what-ifs land in Phase 2 — this layout reserves the nav slot.
        </p>
      </section>
    </div>
  );
}

function FeatureTable({
  title,
  rows,
  release,
}: {
  title: string;
  rows: FeatureRow[];
  release: string;
}) {
  return (
    <div className="tpm-card overflow-hidden">
      <h2 className="border-b border-[var(--tpm-line)] px-4 py-3 text-sm font-semibold">{title}</h2>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-[var(--tpm-sidebar)] text-left text-[11px] uppercase text-[var(--tpm-muted)]">
            <tr>
              <th className="px-3 py-2">Feature</th>
              <th className="px-3 py-2">SIGs</th>
              <th className="px-3 py-2">Stage</th>
              <th className="px-3 py-2">Odds</th>
              <th className="px-3 py-2">Flags</th>
              <th className="px-3 py-2">PRs</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--tpm-line)]">
            {rows.map((f) => (
              <tr key={f.key} className="align-top">
                <td className="px-3 py-2">
                  <Link
                    className="font-medium text-[var(--tpm-accent)] hover:underline"
                    href={`/releases/${release}/features/${f.number}`}
                  >
                    #{f.number}
                  </Link>{" "}
                  {f.title}
                </td>
                <td className="px-3 py-2 text-xs text-[var(--tpm-muted)]">
                  {f.teams.map((t) => t.replace("sig/", "")).join(", ")}
                </td>
                <td className="px-3 py-2 text-xs">{f.stage ?? "—"}</td>
                <td className="px-3 py-2">
                  <OddsCell odds={f.odds} />
                </td>
                <td className="px-3 py-2">
                  <FlagChips flags={f.flags} />
                </td>
                <td className="px-3 py-2 text-xs">
                  {f.prs_merged}/{f.prs_total} merged
                  {f.prs_open ? ` · ${f.prs_open} open` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
