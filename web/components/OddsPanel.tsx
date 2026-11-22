// Before Code Freeze: each feature's odds of landing as a range (10th-90th percentile),
// lowest first, next to the base rate. One series in neutral ink; no colour-only meaning.
import Link from "next/link";
import type { FeatureRow } from "@/lib/api";

const pct = (x: number) => `${Math.round(x * 100)}%`;

export function OddsPanel({ release, rows, validated }: { release: string; rows: FeatureRow[]; validated: boolean }) {
  const withOdds = rows
    .filter((f) => f.in_release && f.odds.status === "forecast" && f.odds.probability !== null)
    .sort((a, b) => (a.odds.probability ?? 0) - (b.odds.probability ?? 0));
  const base = withOdds.find((f) => f.odds.base_rate !== null)?.odds.base_rate ?? null;
  if (!withOdds.length) return <p className="text-sm text-slate-500">No feature has odds right now.</p>;
  return (
    <div className="space-y-2 text-xs">
      {!validated && (
        <p className="rounded bg-amber-50 px-2 py-1 text-amber-900">
          Not validated: the odds do not beat the base rate in every backtest. Read them next to the base rate.
        </p>
      )}
      <ul className="space-y-1.5">
        {withOdds.slice(0, 12).map((f) => {
          const { probability: p, low, high } = f.odds;
          return (
            <li key={f.key} className="grid grid-cols-[1fr_140px_44px] items-center gap-2">
              <Link href={`/releases/${release}/features/${f.number}`} className="truncate text-slate-700 hover:underline" title={f.title}>
                #{f.number} {f.title}
              </Link>
              <div className="relative h-3 rounded-full bg-slate-100" aria-hidden>
                <div className="absolute top-1 h-1 rounded-full bg-slate-400" style={{ left: pct(low ?? 0), width: pct((high ?? 0) - (low ?? 0)) }} />
                <div className="absolute top-0 h-3 w-3 -translate-x-1/2 rounded-full border-2 border-white bg-slate-800" style={{ left: pct(p ?? 0) }} />
                {base !== null && <div className="absolute -top-0.5 h-4 w-px bg-indigo-500" style={{ left: pct(base) }} />}
              </div>
              <span className="text-right font-semibold text-slate-800">
                {pct(p ?? 0)}
                <span className="sr-only">
                  , likely {pct(low ?? 0)} to {pct(high ?? 0)}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      <p className="text-slate-500">
        Dot = odds of landing by Code Freeze, bar = likely range (10th–90th percentile)
        {base !== null ? `, blue line = base rate ${pct(base)}` : ""}. Lowest odds first
        {withOdds.length > 12 ? `; ${withOdds.length - 12} more in the table below` : ""}.
      </p>
    </div>
  );
}
