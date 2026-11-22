"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { RiskNote } from "@/lib/api";
import { formatUtc, refLabel, removedSummary } from "@/lib/format";

/**
 * "Why at risk": AI-written, every claim verified against engine facts before it is shown.
 * Loaded after the page renders and only when the page is opened (owner's choice), so a
 * slow AI call never blocks the facts on the page.
 */
export function RiskNotePanel({ release, number }: { release: string; number: number }) {
  const [note, setNote] = useState<RiskNote | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Through the signed route: only an approver's visit may generate a new (paid) note.
    fetch(`/api/act/releases/${release}/features/${number}/risk-note`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((body: RiskNote) => !cancelled && setNote(body))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [release, number]);

  if (note?.status === "not_at_risk") return null;

  return (
    <section className="rounded border bg-white p-4" aria-live="polite">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="font-medium">Why this feature is at risk</h2>
        <span className="text-[11px] text-slate-500">AI-written · every claim checked against the data</span>
      </div>
      {error ? <p className="text-sm text-rose-700">Could not load the explanation ({error}).</p> : null}
      {!note && !error ? <p className="text-sm text-slate-500">Checking the facts…</p> : null}
      {note && note.status === "sign_in_required" ? (
        <p className="text-sm text-slate-600">
          No explanation written yet.{" "}
          <Link href="/api/auth/signin" prefetch={false} className="font-medium text-indigo-700 hover:underline">
            Sign in as an approver
          </Link>{" "}
          to generate one (it uses paid AI).
        </p>
      ) : null}
      {note && (note.status === "paused" || note.status === "failed") ? (
        <p className="text-sm text-amber-800">No explanation yet: {note.reason}</p>
      ) : null}
      {note && note.claims.length ? (
        <>
          {note.status === "stale" ? (
            <p className="mb-2 rounded bg-amber-50 p-2 text-xs text-amber-900">
              Facts changed since this was written and it could not be refreshed ({note.reason}).
            </p>
          ) : null}
          <ul className="space-y-2">
            {note.claims.map((c) => (
              <li key={c.text} className="text-sm">
                <span className="mr-1 text-emerald-600" aria-label="verified">✓</span>
                {c.text}
                <div className="mt-0.5 flex flex-wrap gap-1 pl-4">
                  {c.refs.map((ref) => {
                    const { label, href } = refLabel(ref);
                    const chip = "rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600";
                    return href ? (
                      <a key={ref} className={`${chip} hover:underline`} href={href} title={ref}>{label}</a>
                    ) : (
                      <span key={ref} className={chip} title={ref}>{label}</span>
                    );
                  })}
                </div>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-slate-500">
            {removedSummary(note.claims_removed, note.removed_by_reason)}{" "}
            {note.generated_at ? `Written ${formatUtc(note.generated_at)} by ${note.model}` : ""}
            {note.attempts > 1 ? ` after ${note.attempts} attempts` : ""}.
          </p>
        </>
      ) : null}
      {note && !note.claims.length && (note.status === "fresh" || note.status === "reused") ? (
        <p className="text-sm text-slate-500">No claim survived the fact check, so nothing is shown.</p>
      ) : null}
    </section>
  );
}
