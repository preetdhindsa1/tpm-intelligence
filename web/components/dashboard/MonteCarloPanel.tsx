"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { FeatureRow, Validation } from "@/lib/api";

type Bin = { bucket: string; mid: number; count: number; density: number };

function landOddsHistogram(features: FeatureRow[]): Bin[] {
  const probs = features
    .filter((f) => f.in_release && f.odds.status === "forecast" && f.odds.probability !== null)
    .map((f) => f.odds.probability as number);
  const edges = [0, 0.2, 0.4, 0.6, 0.8, 1.0001];
  const bins: Bin[] = [];
  for (let i = 0; i < edges.length - 1; i++) {
    const lo = edges[i];
    const hi = edges[i + 1];
    const count = probs.filter((p) => p >= lo && p < hi).length;
    bins.push({
      bucket: `${Math.round(lo * 100)}–${Math.round(hi * 100)}%`,
      mid: (lo + Math.min(hi, 1)) / 2,
      count,
      density: probs.length ? count / probs.length : 0,
    });
  }
  return bins;
}

export function MonteCarloPanel({
  features,
  validation,
}: {
  features: FeatureRow[];
  validation: Validation;
}) {
  const inRelease = features.filter((f) => f.in_release);
  const withOdds = inRelease.filter((f) => f.odds.status === "forecast" && f.odds.probability !== null);
  const data = landOddsHistogram(inRelease);
  const mean =
    withOdds.length === 0
      ? null
      : withOdds.reduce((s, f) => s + (f.odds.probability as number), 0) / withOdds.length;
  const atRisk = withOdds.filter((f) => (f.odds.probability as number) < 0.4).length;
  const base =
    withOdds.find((f) => f.odds.base_rate !== null)?.odds.base_rate ?? null;

  return (
    <section className="tpm-card flex h-full min-h-[28rem] flex-col">
      <header className="border-b border-[var(--tpm-line)] px-4 py-3">
        <h2 className="tpm-panel-title">Monte Carlo land-by-freeze odds</h2>
        <p className="text-[11px] text-[var(--tpm-muted)]">
          Distribution across {withOdds.length} forecast features · engine statistics, not AI
        </p>
      </header>
      <div className="flex flex-1 flex-col gap-3 p-4">
        {!validation.validated ? (
          <p className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-950">
            Odds are <strong>not validated</strong>. {validation.reason}
          </p>
        ) : null}
        <div className="h-48 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="oddsFill" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#b42318" stopOpacity={0.35} />
                  <stop offset="45%" stopColor="#b54708" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#0f6e56" stopOpacity={0.35} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#e4e9ef" strokeDasharray="3 3" />
              <XAxis dataKey="bucket" tick={{ fontSize: 10, fill: "#5b6573" }} />
              <YAxis
                tick={{ fontSize: 10, fill: "#5b6573" }}
                tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                width={36}
              />
              <Tooltip
                formatter={(value) => [
                  `${Math.round(Number(value ?? 0) * 100)}% of features`,
                  "Share",
                ]}
                contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: "#d8dee6" }}
              />
              {mean !== null ? (
                <ReferenceLine
                  x={data.reduce((best, b) =>
                    Math.abs(b.mid - mean) < Math.abs(best.mid - mean) ? b : best
                  ).bucket}
                  stroke="#0f6e56"
                  strokeDasharray="4 4"
                  label={{ value: "Mean", fill: "#0f6e56", fontSize: 10 }}
                />
              ) : null}
              <Area
                type="monotone"
                dataKey="density"
                stroke="#3d5a80"
                fill="url(#oddsFill)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <dl className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-md bg-[var(--tpm-sidebar)] p-2">
            <dt className="text-[var(--tpm-muted)]">Mean land odds</dt>
            <dd className="text-lg font-semibold tabular-nums">
              {mean === null ? "—" : `${Math.round(mean * 100)}%`}
            </dd>
          </div>
          <div className="rounded-md bg-[var(--tpm-sidebar)] p-2">
            <dt className="text-[var(--tpm-muted)]">Features &lt; 40% odds</dt>
            <dd className="text-lg font-semibold tabular-nums text-[var(--tpm-risk)]">{atRisk}</dd>
          </div>
          <div className="col-span-2 rounded-md bg-[var(--tpm-sidebar)] p-2">
            <dt className="text-[var(--tpm-muted)]">Historical base rate (when shown)</dt>
            <dd className="font-medium tabular-nums">
              {base === null ? "—" : `${Math.round(base * 100)}%`} · compare before trusting the curve
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
