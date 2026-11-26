import { formatUtc } from "@/lib/format";
import type { Patterns, Retro } from "@/lib/api-readiness";
import { slipLabel, suppressedText, totalLines, warningLine } from "@/lib/retro";

/** Totals, slips and pool patterns. The API owns every count. */
export function RetroView({ retro, patterns }: { retro: Retro; patterns: Patterns | null }) {
  const hidden = patterns ? suppressedText(patterns.suppressed_groups) : null;
  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center gap-2">
        <h1 className="font-heading text-3xl font-bold tracking-tight">{retro.label ?? "Retro"}</h1>
        {retro.synthetic && <p className="rounded-full bg-warning-bg px-3 py-1 text-sm font-medium text-warning">Synthetic data</p>}
      </header>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {totalLines(retro.totals).map((line) => (
          <li key={line.label} className="rounded-2xl border border-slate-200 bg-white p-4">
            <p className="text-sm text-slate-500">{line.label}</p>
            <p className="font-heading text-3xl font-bold">{line.value}</p>
          </li>
        ))}
      </ul>
      <section>
        <h2 className="font-heading text-lg font-semibold">Slips</h2>
        {retro.slips.length === 0 ? (
          <p className="mt-2 text-sm text-slate-600">No slips.</p>
        ) : (
          <ul className="mt-2 space-y-3">
            {retro.slips.map((slip) => (
              <li key={slip.feature_key} className="rounded-2xl border border-slate-200 bg-white p-4 text-sm">
                <p className="font-semibold">{slip.title}</p>
                <p className="mt-1 text-slate-600">{[slip.pool, slipLabel(slip.slip, slip.moved_to ?? null), formatUtc(slip.slipped_at)].filter(Boolean).join(" · ")}</p>
                <p className="mt-1 text-slate-600">{warningLine(slip)}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section>
        <h2 className="font-heading text-lg font-semibold">Patterns</h2>
        {!patterns && <p className="mt-2 text-sm text-slate-600">Patterns are not available.</p>}
        {patterns && patterns.patterns.length === 0 && <p className="mt-2 text-sm text-slate-600">No pattern is large enough to show.</p>}
        {patterns && patterns.patterns.length > 0 && (
          <ul className="mt-2 space-y-3">
            {patterns.patterns.map((row) => (
              <li key={`${row.pool}-${row.pattern}`} className="rounded-2xl border border-slate-200 bg-white p-4 text-sm">
                <p className="font-semibold">{row.pool}</p>
                <p className="mt-1 text-slate-700">{row.text}</p>
                <p className="mt-1 text-slate-500">{row.n} features · {row.releases.join(", ")}</p>
              </li>
            ))}
          </ul>
        )}
        {hidden && <p className="mt-2 text-sm text-slate-500">{hidden}</p>}
      </section>
    </div>
  );
}
