// Lifecycle card (UX vision p.4): five stages, each filled as far as the release has
// got as of its data date. Steps come from lib/cockpit lifecycle().
import type { LifeStep } from "@/lib/cockpit";

export function LifecycleBar({ steps }: { steps: LifeStep[] }) {
  if (steps.length === 0) return null;
  return (
    <ol aria-label="Lifecycle" className="grid grid-cols-2 gap-4 rounded-2xl border border-slate-200 bg-white px-6 py-5 sm:grid-cols-5">
      {steps.map((s) => (
        <li key={s.name} aria-current={s.here ? "step" : undefined}>
          <div className="h-1.5 overflow-hidden rounded-full bg-slate-200" role="img" aria-label={`${s.name} ${Math.round(s.fill * 100)}% done`}>
            <div className="h-full rounded-full bg-action" style={{ width: `${Math.round(s.fill * 100)}%` }} />
          </div>
          <p className={`mt-2.5 text-sm font-semibold ${s.here ? "text-action" : "text-slate-900"}`}>
            {s.name}{s.here ? " · you are here" : ""}
          </p>
          <p className="text-sm text-slate-500">{s.note}</p>
        </li>
      ))}
    </ol>
  );
}
