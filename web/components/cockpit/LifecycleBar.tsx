// Lifecycle card (UX vision p.4): five stages, each filled as far as the release has
// got as of its data date. Steps come from lib/cockpit lifecycle(). Launch and Learn
// are live, and link to readiness or retro, only when the portfolio API says that
// module has real data. Otherwise they say "not started".
import Link from "next/link";
import type { LifeStep } from "@/lib/cockpit";
import { NOT_STARTED, type LaunchLearn, type ModuleState } from "@/lib/stages";

function moduleFor(name: string, modules?: LaunchLearn): ModuleState | null {
  const key = name.toLowerCase();
  if (!modules || (key !== "launch" && key !== "learn")) return null;
  return modules[key];
}

export function LifecycleBar({ steps, modules }: { steps: LifeStep[]; modules?: LaunchLearn }) {
  if (steps.length === 0) return null;
  return (
    <ol aria-label="Lifecycle" className="grid grid-cols-2 gap-4 rounded-2xl border border-slate-200 bg-white px-6 py-5 sm:grid-cols-5">
      {steps.map((s) => {
        const mod = moduleFor(s.name, modules);
        return (
          <li key={s.name} aria-current={s.here ? "step" : undefined}>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-200" role="img" aria-label={`${s.name} ${Math.round(s.fill * 100)}% done`}>
              <div className="h-full rounded-full bg-action" style={{ width: `${Math.round(s.fill * 100)}%` }} />
            </div>
            <p className={`mt-2.5 text-sm font-semibold ${s.here ? "text-action" : "text-slate-900"}`}>
              {mod?.live && mod.href ? (
                <Link href={mod.href} className="hover:underline">{s.name}</Link>
              ) : (
                s.name
              )}
              {s.here ? " · you are here" : ""}
            </p>
            {mod && <p className="text-xs font-medium text-slate-500">{mod.live ? "Live" : NOT_STARTED}</p>}
            <p className="text-sm text-slate-500">{s.note}</p>
          </li>
        );
      })}
    </ol>
  );
}
