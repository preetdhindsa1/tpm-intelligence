import { formatUtc } from "@/lib/format";
import type { SaidVsShowed } from "@/lib/api-readiness";
import { byMeetingDate } from "@/lib/said";

const FACTS: Record<string, string> = {
  replay_day: "Replay day",
  features_at_risk: "Features at risk",
  critical_flags: "Critical flags",
  in_release: "Features in the release",
};

/** Meetings on the left, the same day's snapshot facts on the right. Quotes stay verbatim. */
export function SaidTimeline({ data }: { data: SaidVsShowed }) {
  const rows = byMeetingDate(data.rows);
  if (rows.length === 0) return <p className="text-sm text-slate-600">No meetings to compare.</p>;
  return (
    <ol className="space-y-4">
      {rows.map((row) => (
        <li key={row.date} className="rounded-2xl border border-slate-200 bg-white p-4">
          <p className="text-sm font-semibold text-slate-500">{formatUtc(row.date)}</p>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <div>
              <h3 className="text-sm font-semibold">Said</h3>
              {row.said.length === 0 ? (
                <p className="mt-1 text-sm text-slate-600">Nothing said.</p>
              ) : (
                <ul className="mt-1 space-y-2">
                  {row.said.map((item) => (
                    <li key={item.item_id} className="text-sm">
                      <p>
                        <span className="capitalize">{item.type}</span>
                        {item.review === "suggested" && <span className="ml-2 rounded-full bg-warning-bg px-2 py-0.5 text-xs font-medium text-warning">Suggested</span>}
                      </p>
                      {item.quote && <p className="mt-1 text-slate-800">{item.quote}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <h3 className="text-sm font-semibold">Showed</h3>
              {row.showed.length === 0 ? (
                <p className="mt-1 text-sm text-slate-600">Nothing shown.</p>
              ) : (
                <ul className="mt-1 space-y-1 text-sm text-slate-700">
                  {row.showed.map((fact) => (
                    <li key={fact.name}>{FACTS[fact.name] ?? fact.name.replaceAll("_", " ")}: {fact.value === null ? "not measured" : String(fact.value)}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
