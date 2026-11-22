"use client";

import type { FeatureRow, Release, Validation } from "@/lib/api";
import { ReleaseHeader } from "@/components/dashboard/ReleaseHeader";
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
  const label = `${release.display_name || release.project || "Team"} ${release.name}`;

  return (
    <div className="flex h-full min-h-screen flex-col">
      <ReleaseHeader releaseName={releaseName} release={release} title="Dashboard" />
      <div className="grid flex-1 gap-4 p-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(16rem,0.85fr)_minmax(16rem,0.85fr)]">
        <DependencyGraph features={features} releaseLabel={label} />
        <MonteCarloPanel features={features} validation={validation} />
        <ExecutiveBrief release={releaseName} features={features} />
      </div>
    </div>
  );
}
