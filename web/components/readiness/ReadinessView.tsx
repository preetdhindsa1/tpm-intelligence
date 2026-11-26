import { DecisionForm } from "@/components/readiness/DecisionForm";
import { formatUtc } from "@/lib/format";
import type { Readiness } from "@/lib/api-readiness";
import { UNKNOWN_REASON, criterionLabel, decisionLabel, newestDecisions, verdictLabel } from "@/lib/readiness";

/** Criteria, verdict and the append-only decision log. Counts come from the API. */
export function ReadinessView({ data }: { data: Readiness }) {
  const decisions = newestDecisions(data.decisions);
  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center gap-2">
        <h1 className="font-heading text-3xl font-bold tracking-tight">Release readiness</h1>
        <p className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold text-slate-800">{verdictLabel(data.verdict)}</p>
        {data.synthetic && <p className="rounded-full bg-warning-bg px-3 py-1 text-sm font-medium text-warning">Synthetic data</p>}
        {!data.validated && <p className="rounded-full bg-warning-bg px-3 py-1 text-sm font-medium text-warning">Not validated</p>}
      </header>
      {!data.validated && <p className="text-sm text-slate-600">{data.validation_note}</p>}
      {data.summary && data.summary.length > 0 && (
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <h2 className="font-heading text-lg font-semibold">AI summary</h2>
          <ul className="mt-2 space-y-1 text-sm text-slate-700">
            {data.summary.map((claim) => (
              <li key={claim.text}>{claim.text}</li>
            ))}
          </ul>
        </section>
      )}
      <ul className="space-y-3">
        {data.criteria.map((item) => (
          <li key={item.id} className="rounded-2xl border border-slate-200 bg-white p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-heading text-lg font-semibold">{item.name}</h2>
              <p className="text-sm font-semibold">{criterionLabel(item.status)}</p>
            </div>
            <p className="mt-1 text-sm text-slate-600">{item.detail}</p>
            {item.status === "unknown" && <p className="mt-1 text-sm text-slate-500">{UNKNOWN_REASON}</p>}
            {item.evidence.length > 0 && (
              <ul className="mt-3 space-y-1 text-sm">
                {item.evidence.map((ev) => (
                  <li key={`${ev.ref}-${ev.text}`}>
                    {ev.url ? (
                      <a href={ev.url} className="text-action hover:underline">{ev.text}</a>
                    ) : (
                      ev.text
                    )}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
      <DecisionForm release={data.release} />
      <section>
        <h2 className="font-heading text-lg font-semibold">Decision log</h2>
        {decisions.length === 0 ? (
          <p className="mt-2 text-sm text-slate-600">No decision yet.</p>
        ) : (
          <ol className="mt-2 space-y-3">
            {decisions.map((row) => (
              <li key={`${row.decided_at}-${row.decision}`} className="rounded-2xl border border-slate-200 bg-white p-4 text-sm">
                <p className="font-semibold">{decisionLabel(row.decision)} · {row.decided_by}</p>
                <p className="mt-1 text-slate-700">{row.note}</p>
                <p className="mt-1 text-slate-500">{formatUtc(row.decided_at)}</p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
