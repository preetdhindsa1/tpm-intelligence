"use client";

import { featureLabel } from "@/lib/vocab";
// Days-of-delay chart (M7, from the owner's mockup): how many features will have their
// required code merged by each day, relative to Code Freeze. Two series, so a legend and
// direct labels; the forecast band is the 10th-90th percentile of the simulated count.
import { Area, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { MergeDates } from "@/lib/api";
import { dateOf, delayRows, expectedOn, likelyLate, relDay, type DelayRow } from "@/lib/delay";

const FORECAST = "#4f46e5";
const ACTUAL = "#0f172a";
const BAND = "#c7d2fe";

function Tip({ active, payload, m }: { active?: boolean; payload?: { payload: DelayRow }[]; m: MergeDates }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  const on = expectedOn(m.items, r.day);
  return (
    <div className="max-w-xs rounded-md border bg-white p-2 text-xs shadow">
      <p className="font-semibold text-slate-800">
        {dateOf(r.day, m.code_freeze_at)} · {relDay(r.day)}
      </p>
      {r.actual !== undefined && <p className="text-slate-700">Merged so far: {r.actual}</p>}
      {r.expected !== undefined && r.band && (
        <p className="text-slate-700">
          Forecast: {r.expected.toFixed(1)} (likely {Math.round(r.band[0])}–{Math.round(r.band[1])}) of {m.features}
        </p>
      )}
      {on.length > 0 && (
        <>
          <p className="mt-1 text-slate-500">Median merge day for:</p>
          <ul>
            {on.slice(0, 6).map((f) => (
              <li key={f.key} className="truncate text-slate-700">
                {featureLabel(f)} {f.title}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export function DelayChart({ m, recorded }: { m: MergeDates; recorded?: string }) {
  const rows = delayRows(m);
  const late = likelyLate(m.items).filter((f) => (f.by_release ?? 1) < 0.5);
  const open = m.items.filter((f) => f.status === "forecast").length;
  if (!rows.length) return <p className="text-sm text-slate-500">No dates to chart for this release.</p>;
  return (
    <div className="space-y-3">
      {!m.validation.validated && (
        <p className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-900">
          <strong>Not validated:</strong> {(m.validation.reason ?? "merge-date forecasts have not passed their backtest").replace(/\.$/, "")}.
          Read the band as a rough guide.
        </p>
      )}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 22, right: 24, bottom: 4, left: 0 }}>
              <XAxis
                dataKey="day"
                type="number"
                domain={["dataMin", "dataMax"]}
                tickFormatter={(d: number) => dateOf(d, m.code_freeze_at)}
                tick={{ fontSize: 11, fill: "#475569" }}
                tickLine={false}
                axisLine={{ stroke: "#c3c2b7" }}
              />
              <YAxis
                allowDecimals={false}
                domain={[0, m.features]}
                tick={{ fontSize: 11, fill: "#475569" }}
                tickLine={false}
                axisLine={false}
                width={32}
              />
              <Tooltip content={<Tip m={m} />} cursor={{ stroke: "#94a3b8", strokeDasharray: "3 3" }} />
              <ReferenceLine x={0} stroke="#d03b3b" strokeDasharray="4 3" label={{ value: "Code Freeze", position: "top", fontSize: 11, fill: "#b02a2a" }} />
              {m.release_day !== null && (
                <ReferenceLine
                  x={Math.floor(m.release_day)}
                  stroke="#0ca30c"
                  strokeDasharray="4 3"
                  label={{ value: "Release day", position: "top", fontSize: 11, fill: "#08780a" }}
                />
              )}
              {m.as_of_day !== null && (
                <ReferenceLine x={Math.floor(m.as_of_day)} stroke="#94a3b8" label={{ value: "Today", position: "insideBottomRight", fontSize: 11, fill: "#475569" }} />
              )}
              <ReferenceLine y={m.features} stroke="#e2e8f0" />
              <Area dataKey="band" stroke="none" fill={BAND} fillOpacity={0.6} isAnimationActive={false} name="Likely range" />
              <Line dataKey="expected" stroke={FORECAST} strokeWidth={2} dot={false} isAnimationActive={false} name="Forecast" />
              <Line dataKey="actual" stroke={ACTUAL} strokeWidth={2} dot={false} isAnimationActive={false} name="Merged so far" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="space-y-2 text-sm">
          <ul className="space-y-1 text-xs text-slate-600">
            <li className="flex items-center gap-2">
              <span className="h-0.5 w-5" style={{ background: ACTUAL }} /> Merged so far ({m.done_now} of {m.features})
            </li>
            <li className="flex items-center gap-2">
              <span className="h-0.5 w-5" style={{ background: FORECAST }} /> Forecast (expected count)
            </li>
            <li className="flex items-center gap-2">
              <span className="h-3 w-5 rounded-sm" style={{ background: BAND }} /> Likely range (10th–90th percentile)
            </li>
          </ul>
          <p className="border-t pt-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Likely to miss release day ({late.length} of {open} still open)
          </p>
          <ul className="max-h-40 space-y-1 overflow-y-auto text-xs">
            {late.slice(0, 10).map((f) => (
              <li key={f.key} className="flex justify-between gap-2">
                <span className="truncate text-slate-700" title={f.title}>
                  {featureLabel(f)} {f.title}
                </span>
                <span className="shrink-0 font-medium text-slate-800">{Math.round((f.by_release ?? 0) * 100)}%</span>
              </li>
            ))}
            {!late.length && <li className="text-slate-500">None below 50% odds of merging by release day.</li>}
          </ul>
          <p className="text-[11px] text-slate-500">% = odds the required code merges by release day.</p>
        </div>
      </div>
      <details className="text-xs text-slate-600">
        <summary className="cursor-pointer">Show as table</summary>
        <table className="mt-1 w-full text-left">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 pr-2">Day</th>
              <th className="py-1 pr-2">Merged so far</th>
              <th className="py-1 pr-2">Forecast</th>
              <th className="py-1">Likely range</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.day} className="border-t">
                <td className="py-0.5 pr-2">
                  {dateOf(r.day, m.code_freeze_at)} ({relDay(r.day)})
                </td>
                <td className="py-0.5 pr-2">{r.actual ?? ""}</td>
                <td className="py-0.5 pr-2">{r.expected?.toFixed(1) ?? ""}</td>
                <td className="py-0.5">{r.band ? `${Math.round(r.band[0])}–${Math.round(r.band[1])}` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
      <p className="text-[11px] text-slate-500">
        {m.note}
        {recorded ? ` ${recorded}` : ""}
      </p>
    </div>
  );
}
