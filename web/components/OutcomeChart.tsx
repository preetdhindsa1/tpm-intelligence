"use client";

// What happened at Code Freeze, per outcome (facts from rule flags and membership
// history). One series, so no legend: each bar is named on the axis and coloured by
// status, never by colour alone.
import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Summary } from "@/lib/api";
import { OUTCOME_META, outcomeRows } from "@/lib/dashboard";

type Row = ReturnType<typeof outcomeRows>[number];

function Tip({ active, payload }: { active?: boolean; payload?: { payload: Row }[] }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="max-w-xs rounded-md border bg-white p-2 text-xs shadow">
      <p className="font-semibold text-slate-800">
        {r.label}: {r.count}
      </p>
      <p className="mb-1 text-slate-500">{OUTCOME_META[r.outcome].help}</p>
      <ul className="space-y-0.5 text-slate-700">
        {r.features.slice(0, 8).map((f) => (
          <li key={f} className="truncate">
            {f}
          </li>
        ))}
        {r.features.length > 8 && <li className="text-slate-500">and {r.features.length - 8} more</li>}
      </ul>
    </div>
  );
}

export function OutcomeChart({ summary }: { summary: Summary }) {
  const rows = outcomeRows(summary);
  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 36, bottom: 4, left: 4 }} barCategoryGap={6}>
            <XAxis type="number" hide allowDecimals={false} />
            <YAxis
              type="category"
              dataKey="label"
              width={190}
              tickLine={false}
              axisLine={{ stroke: "#c3c2b7" }}
              tick={{ fontSize: 12, fill: "#475569" }}
            />
            <Tooltip content={<Tip />} cursor={{ fill: "#f1f0eb" }} />
            <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={22} isAnimationActive={false}>
              {rows.map((r) => (
                <Cell key={r.outcome} fill={r.color} />
              ))}
              <LabelList dataKey="count" position="right" style={{ fontSize: 12, fill: "#334155", fontWeight: 600 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-2 text-xs text-slate-600">
        <summary className="cursor-pointer">Show as table</summary>
        <table className="mt-1 w-full text-left">
          <tbody>
            {rows.map((r) => (
              <tr key={r.outcome} className="border-t align-top">
                <td className="py-1 pr-2 font-medium">{r.label}</td>
                <td className="py-1 pr-2">{r.count}</td>
                <td className="py-1">{r.features.join("; ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
