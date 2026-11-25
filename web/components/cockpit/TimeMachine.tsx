"use client";

// Time machine (UX vision p.4): a feature's real release story, one moment at a time.
// Stops come from lib/cockpit keyStops (the feature's timeline); this file only shows them.
import { useState } from "react";
import { dayMonth, type KeyStop } from "@/lib/cockpit";

export function TimeMachine({ feature, title, context, stops, error }: {
  feature: number; title: string; context: string; stops: KeyStop[]; error: string | null;
}) {
  const start = Math.max(0, stops.findIndex((s) => s.key === "main-open"));
  const [i, setI] = useState(start);
  const stop = stops[i];
  return (
    <section className="rounded-2xl bg-ink p-6 text-white md:p-8">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wider text-indigo-300">Time machine · as-of replay</p>
        <p className="text-sm text-slate-400">{title}{context ? ` · ${context}` : ""}</p>
      </div>
      <h2 className="mt-2 font-heading text-2xl font-bold md:text-3xl">What did we know, and when? Feature #{feature}</h2>
      {error && <p className="mt-4 text-sm text-slate-200">{error}</p>}
      {!error && stops.length === 0 && <p className="mt-4 text-sm text-slate-200">No timeline events for #{feature}.</p>}
      {stops.length > 0 && (
        <>
          <ol className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8" aria-label={`Moments in feature #${feature}'s release`}>
            {stops.map((s, n) => {
              const on = n === i;
              const tone = on
                ? "border-indigo-400 bg-action text-white"
                : s.tone === "critical"
                  ? "border-red-900/70 bg-red-950/60 text-red-300 hover:border-red-700"
                  : "border-white/10 bg-white/[0.04] text-white hover:border-white/30";
              return (
                <li key={s.key}>
                  <button type="button" aria-pressed={on} onClick={() => setI(n)}
                    className={`flex h-full min-h-16 w-full flex-col items-start rounded-lg border px-3 py-2.5 text-left ${tone}`}>
                    <span className={`text-xs ${on ? "text-indigo-100" : s.tone === "critical" ? "text-red-300" : "text-slate-400"}`}>{dayMonth(s.at)}</span>
                    <span className="mt-0.5 text-sm font-semibold leading-snug">{s.label}</span>
                  </button>
                </li>
              );
            })}
          </ol>
          {stop && (
            <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]" aria-live="polite">
              <div className="rounded-xl border border-white/10 bg-white/[0.04] p-5">
                <p className="text-sm text-slate-400">{stop.when}</p>
                <p className="mt-1 font-heading text-xl font-semibold">{stop.headline}</p>
                <p className="mt-2 leading-7 text-slate-200">{stop.knew}</p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.04] p-5">
                <p className="text-sm text-slate-400">Why it matters</p>
                <p className="mt-2 leading-7 text-slate-100">{stop.why}</p>
              </div>
            </div>
          )}
          <p className="mt-4 text-xs text-slate-400">Real public events from GitHub (UTC). Replay uses only data available on the chosen day.</p>
        </>
      )}
    </section>
  );
}
