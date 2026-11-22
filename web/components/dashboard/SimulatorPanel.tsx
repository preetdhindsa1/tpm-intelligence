"use client";

import { useMemo, useState } from "react";
import type { FeatureRow, Validation } from "@/lib/api";

/**
 * Shadow-Org UI shell. Numbers stay illustrative placeholders until the SimPy
 * simulator is validated (CLAUDE.md §14). Sliders are interactive for layout demo
 * only and do not change engine odds.
 */
export function SimulatorPanel({
  features,
  validation,
}: {
  features: FeatureRow[];
  validation: Validation;
}) {
  const [reviewers, setReviewers] = useState(4);
  const [sharedTeams, setSharedTeams] = useState(2);
  const [interruption, setInterruption] = useState(15);
  const [sprints, setSprints] = useState(3);

  const inRelease = features.filter((f) => f.in_release);
  const withOdds = inRelease.filter((f) => f.odds.status === "forecast" && f.odds.probability !== null);
  const baselineMean = useMemo(() => {
    if (!withOdds.length) return null;
    return withOdds.reduce((s, f) => s + (f.odds.probability as number), 0) / withOdds.length;
  }, [withOdds]);

  // Demo-only delta: fewer reviewers → show wider "scenario" band as UI preview, labeled not validated.
  const pressure = Math.max(0, (4 - reviewers) / 4) + interruption / 200 + (sharedTeams - 1) * 0.03;
  const scenarioMean =
    baselineMean === null ? null : Math.max(0.05, Math.min(0.95, baselineMean * (1 - pressure * 0.25)));

  return (
    <div className="grid gap-4 p-4 lg:grid-cols-[20rem_minmax(0,1fr)]">
      <section className="tpm-card space-y-4 p-4">
        <h2 className="tpm-panel-title">Scenario controls</h2>
        <p className="text-[11px] text-[var(--tpm-muted)]">
          Shadow-Org simulator is not validated yet. Sliders preview the layout; they do not run SimPy.
        </p>
        <Slider label="Reviewers" value={reviewers} min={1} max={12} onChange={setReviewers} />
        <Slider
          label="Teams sharing reviewers"
          value={sharedTeams}
          min={1}
          max={8}
          onChange={setSharedTeams}
        />
        <Slider
          label="Interruption rate %"
          value={interruption}
          min={0}
          max={60}
          onChange={setInterruption}
        />
        <Slider label="Sprints in window" value={sprints} min={1} max={8} onChange={setSprints} />
        <button
          type="button"
          className="w-full rounded-md border border-[var(--tpm-line)] bg-[var(--tpm-sidebar)] px-3 py-2 text-sm font-medium text-[var(--tpm-muted)]"
          disabled
          title="Available after simulator validation"
        >
          Apply suggested fix (coming soon)
        </button>
      </section>

      <section className="tpm-card flex flex-col p-4">
        <h2 className="tpm-panel-title">Baseline vs scenario</h2>
        <p className="mb-3 text-[11px] text-[var(--tpm-muted)]">
          Baseline uses current engine land odds. Scenario column is a UI placeholder until Phase 2
          validation passes (±20% median on a past release).
        </p>
        {!validation.validated ? (
          <p className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-950">
            Forecast odds are <strong>not validated</strong>. Simulator what-ifs will stay marked not
            validated until CLAUDE.md §14 checks pass.
          </p>
        ) : null}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-[var(--tpm-line)] bg-[var(--tpm-sidebar)] p-4">
            <p className="text-[11px] uppercase text-[var(--tpm-muted)]">Baseline</p>
            <p className="mt-1 text-3xl font-semibold tabular-nums">
              {baselineMean === null ? "—" : `${Math.round(baselineMean * 100)}%`}
            </p>
            <p className="text-xs text-[var(--tpm-muted)]">Mean land-by-freeze odds · {withOdds.length} features</p>
          </div>
          <div className="rounded-lg border border-dashed border-[var(--tpm-warn)] bg-[#fff8f1] p-4">
            <p className="text-[11px] uppercase text-[var(--tpm-warn)]">Scenario (not simulated)</p>
            <p className="mt-1 text-3xl font-semibold tabular-nums text-[var(--tpm-warn)]">
              {scenarioMean === null ? "—" : `${Math.round(scenarioMean * 100)}%`}
            </p>
            <p className="text-xs text-[var(--tpm-muted)]">
              Preview only · {reviewers} reviewers · {interruption}% interruption · {sprints} sprints
            </p>
          </div>
        </div>
        <div className="mt-4 rounded-md border border-[var(--tpm-line)] p-3 text-xs text-[var(--tpm-muted)]">
          <p className="font-medium text-[var(--tpm-ink)]">Assumptions (to be measured)</p>
          <ul className="mt-1 list-disc pl-4">
            <li>Review rounds, wait per round, time to merge — from stored events</li>
            <li>PR arrival rate / week including unlinked PRs</li>
            <li>Reviewer workload and interruption proxy — ADR after first calibration</li>
            <li>Source releases and measured_at will appear here once calibrate runs</li>
          </ul>
        </div>
      </section>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (n: number) => void;
}) {
  return (
    <label className="block text-sm">
      <span className="flex justify-between text-[var(--tpm-muted)]">
        <span>{label}</span>
        <span className="font-medium tabular-nums text-[var(--tpm-ink)]">{value}</span>
      </span>
      <input
        className="mt-1 w-full accent-[var(--tpm-accent)]"
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}
