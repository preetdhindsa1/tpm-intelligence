"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { publicApiUrl, type FeatureRow, type RiskNote, type VerifiedClaim } from "@/lib/api";
import { removedSummary } from "@/lib/format";

type BriefItem = {
  featureNumber: number;
  featureTitle: string;
  claim: VerifiedClaim;
};

function isAtRisk(f: FeatureRow): boolean {
  return (
    f.in_release &&
    (f.flags.some((x) => x.severity === "critical" || x.severity === "warning") ||
      (f.odds.status === "forecast" && f.odds.probability !== null && f.odds.probability < 0.45))
  );
}

export function ExecutiveBrief({
  release,
  features,
}: {
  release: string;
  features: FeatureRow[];
}) {
  const targets = useMemo(
    () =>
      [...features]
        .filter(isAtRisk)
        .sort((a, b) => {
          const ap = a.odds.probability ?? 1;
          const bp = b.odds.probability ?? 1;
          return ap - bp;
        })
        .slice(0, 4),
    [features]
  );

  const [items, setItems] = useState<BriefItem[]>([]);
  const [removed, setRemoved] = useState(0);
  const [byReason, setByReason] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!targets.length) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) {
        setLoading(true);
        setError(null);
      }
    });
    Promise.all(
      targets.map(async (f) => {
        const res = await fetch(`${publicApiUrl}/releases/${release}/features/${f.number}/risk-note`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const note = (await res.json()) as RiskNote;
        return { f, note };
      })
    )
      .then((rows) => {
        if (cancelled) return;
        const next: BriefItem[] = [];
        let rem = 0;
        const reasons: Record<string, number> = {};
        for (const { f, note } of rows) {
          rem += note.claims_removed;
          for (const [k, v] of Object.entries(note.removed_by_reason ?? {})) {
            reasons[k] = (reasons[k] ?? 0) + v;
          }
          for (const claim of note.claims) {
            next.push({ featureNumber: f.number, featureTitle: f.title, claim });
          }
        }
        setItems(next);
        setRemoved(rem);
        setByReason(reasons);
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [release, targets]);

  const engineFacts = useMemo(() => {
    return features
      .filter((f) => f.in_release)
      .flatMap((f) =>
        f.flags
          .filter((fl) => fl.severity === "critical" || fl.severity === "warning")
          .map((fl) => ({ feature: f, flag: fl }))
      )
      .slice(0, 8);
  }, [features]);

  return (
    <section className="tpm-card flex h-full min-h-[28rem] flex-col">
      <header className="border-b border-[var(--tpm-line)] px-4 py-3">
        <h2 className="tpm-panel-title">Verified AI executive brief</h2>
        <p className="text-[11px] text-[var(--tpm-muted)]">
          AI text only after fact-check · engine flags listed separately
        </p>
      </header>
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        <div>
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--tpm-muted)]">
            Engine facts
          </h3>
          <ul className="space-y-2">
            {engineFacts.map(({ feature, flag }) => (
              <li key={`${feature.key}-${flag.code}`} className="flex gap-2 text-sm">
                <span className="mt-0.5 text-[var(--tpm-risk)]" aria-hidden>
                  ●
                </span>
                <div>
                  <Link
                    className="font-medium text-[var(--tpm-accent)] hover:underline"
                    href={`/releases/${release}/features/${feature.number}`}
                  >
                    #{feature.number}
                  </Link>{" "}
                  <span className="text-[var(--tpm-muted)]">{flag.code.replaceAll("_", " ")}</span>
                  <p className="text-xs text-[var(--tpm-ink)]">{flag.message}</p>
                </div>
              </li>
            ))}
            {!engineFacts.length ? (
              <li className="text-sm text-[var(--tpm-muted)]">No critical or warning flags on in-release features.</li>
            ) : null}
          </ul>
        </div>

        <div>
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--tpm-muted)]">
            Verified AI claims
          </h3>
          {loading ? <p className="text-sm text-[var(--tpm-muted)]">Checking claims…</p> : null}
          {error ? <p className="text-sm text-[var(--tpm-risk)]">Could not load AI brief ({error}).</p> : null}
          {!loading && !error && !items.length ? (
            <p className="text-sm text-[var(--tpm-muted)]">
              No verified AI claims yet for the top at-risk features. Open a feature page to generate a
              risk note on demand.
            </p>
          ) : null}
          <ul className="space-y-3">
            {items.map((item) => (
              <li key={`${item.featureNumber}-${item.claim.text}`} className="text-sm">
                <div className="flex gap-2">
                  <span className="mt-0.5 text-[var(--tpm-accent)]" aria-label="verified">
                    ✓
                  </span>
                  <div>
                    <Link
                      href={`/releases/${release}/features/${item.featureNumber}`}
                      className="text-[11px] font-medium text-[var(--tpm-muted)] hover:underline"
                    >
                      #{item.featureNumber} {item.featureTitle}
                    </Link>
                    <p>{item.claim.text}</p>
                    <p className="mt-0.5 text-[11px] text-[var(--tpm-accent)]">[Verified]</p>
                  </div>
                </div>
              </li>
            ))}
          </ul>
          {removed > 0 ? (
            <p className="mt-3 text-[11px] text-[var(--tpm-muted)]">{removedSummary(removed, byReason)}</p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
