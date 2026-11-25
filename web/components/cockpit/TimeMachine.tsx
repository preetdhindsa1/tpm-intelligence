"use client";

import { useState } from "react";

export type MachineStop = { at: string; label: string };

export function TimeMachine({ stops, error }: { stops: MachineStop[]; error: string | null }) {
  const [i, setI] = useState(0);
  const stop = stops[i];
  return (
    <section className="rounded-lg bg-ink p-4 text-white">
      <h2 className="font-heading text-lg font-semibold">Time machine · #6395</h2>
      {error && <p className="mt-2 text-sm text-slate-200">{error}</p>}
      {!error && stops.length === 0 && <p className="mt-2 text-sm text-slate-200">No timeline events for #6395.</p>}
      {stop && (
        <>
          <p className="mt-3 text-sm text-slate-300">{i + 1} of {stops.length}</p>
          <p className="mt-1 text-xl font-semibold">{stop.label}</p>
          <p className="text-sm text-slate-300">{stop.at}</p>
          <div className="mt-3 flex gap-2">
            <button type="button" className="inline-flex min-h-11 items-center rounded-md border border-white/30 px-3 text-sm" disabled={i === 0} onClick={() => setI((n) => n - 1)}>Earlier</button>
            <button type="button" className="inline-flex min-h-11 items-center rounded-md bg-action px-3 text-sm font-medium" disabled={i === stops.length - 1} onClick={() => setI((n) => n + 1)}>Later</button>
          </div>
        </>
      )}
    </section>
  );
}
