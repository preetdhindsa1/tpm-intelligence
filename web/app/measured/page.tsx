// Every measured result, including what failed (linked from the front page's
// "Measure, don't claim" card). Values come from lib/measured.ts, which mirrors the
// dated result files in docs/results/.
import Link from "next/link";
import { verdictSummary } from "@/lib/front";
import { MEASURED, VERDICT_LABEL, VERDICT_TONE, type Verdict } from "@/lib/measured";

const ORDER: Verdict[] = ["fail", "partial", "pending", "pass"];
const GROUP: Record<Verdict, string> = { fail: "Fails", partial: "Partly", pending: "Not measured yet", pass: "Passes" };

export default function MeasuredPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-8 py-4">
      <header>
        <Link href="/#measured" className="inline-flex min-h-11 items-center text-sm text-action hover:underline">← Measure, don&apos;t claim</Link>
        <h1 className="font-heading text-4xl font-bold tracking-tight">Every measured result, including what failed</h1>
        <p className="mt-2 max-w-3xl text-slate-600">
          Each number is dated and comes from a result file in the repository. Failures stay on this page, and a model that has not
          passed its check is labeled &quot;not validated&quot; wherever it appears.
        </p>
        <p className="mt-3 font-medium text-slate-800">{verdictSummary(MEASURED)}</p>
      </header>
      {ORDER.map((v) => {
        const rows = MEASURED.filter((m) => m.verdict === v);
        if (rows.length === 0) return null;
        return (
          <section key={v}>
            <h2 className="font-heading text-xl font-semibold">{GROUP[v]} ({rows.length})</h2>
            <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {rows.map((item) => (
                <li key={item.id} className="flex flex-col rounded-xl border border-slate-200 bg-white p-5">
                  <p><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${VERDICT_TONE[item.verdict]}`}>{VERDICT_LABEL[item.verdict]}</span></p>
                  <p className="mt-2 font-heading text-2xl font-semibold">{item.value}</p>
                  <p className="text-sm text-slate-800">{item.label}</p>
                  <p className="mt-1 flex-1 text-sm leading-6 text-slate-500">{item.detail}</p>
                  <p className="mt-2 text-xs text-slate-400">{item.measured ? `Measured ${item.measured}` : "TBD (not yet measured)"}</p>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
