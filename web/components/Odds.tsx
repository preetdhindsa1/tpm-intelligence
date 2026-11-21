import type { Odds as OddsT } from "@/lib/api";
import { oddsDisplay } from "@/lib/format";

const TONE = { good: "text-emerald-700", watch: "text-amber-700", risk: "text-rose-700", none: "text-slate-500" };

export function OddsCell({ odds }: { odds: OddsT }) {
  const d = oddsDisplay(odds);
  return (
    <div>
      <div className={`font-semibold ${TONE[d.tone]}`}>
        {d.headline}
        {!d.validated && odds.status === "forecast" ? (
          <span className="ml-2 rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium uppercase text-slate-600">not validated</span>
        ) : null}
      </div>
      <div className="text-xs text-slate-500">{d.detail}</div>
    </div>
  );
}
