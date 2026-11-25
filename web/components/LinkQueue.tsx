"use client";

import { useEffect, useState } from "react";
import { updatesRequest, type LinkSuggestion, type LinkSuggestions } from "@/lib/api";
import { ApproverNote, useMe } from "@/components/Me";
import { formatUtc, suggestionCounts } from "@/lib/format";

type Tab = "suggested" | "confirmed" | "rejected";
const TABS: { id: Tab; label: string }[] = [
  { id: "suggested", label: "Waiting for review" },
  { id: "confirmed", label: "Confirmed" },
  { id: "rejected", label: "Rejected" },
];
const ENH = "https://github.com/kubernetes/enhancements/issues";

export function LinkQueue({ release }: { release: string }) {
  const me = useMe();
  const canAct = me?.approver ?? false;
  const [data, setData] = useState<LinkSuggestions | null>(null);
  const [tab, setTab] = useState<Tab>("suggested");
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});

  useEffect(() => {
    let cancelled = false;
    updatesRequest<LinkSuggestions>(`/releases/${release}/link-suggestions`)
      .then((d) => !cancelled && setData(d))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [release]);

  async function decide(s: LinkSuggestion, action: "confirm" | "reject") {
    setBusy(s.id);
    setError(null);
    try {
      const done = await updatesRequest<LinkSuggestion>(
        `/releases/${release}/link-suggestions/${s.id}/${action}`,
        { method: "POST", body: JSON.stringify({ note: notes[s.id] || null }) },
      );
      setData((d) => {
        if (!d) return d;
        const counts = { ...d.counts };
        counts.suggested = (counts.suggested ?? 1) - 1;
        counts[done.status] = (counts[done.status] ?? 0) + 1;
        return { ...d, counts, suggestions: d.suggestions.map((x) => (x.id === done.id ? done : x)) };
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (error && !data) return <p className="rounded border border-rose-200 bg-rose-50 p-2 text-sm text-rose-800">{error}</p>;
  if (!data) return <p className="text-sm text-slate-500">Loading…</p>;
  const shown = data.suggestions.filter((s) => s.status === tab);

  return (
    <div className="space-y-4">
      <ApproverNote me={me} action="confirm or reject links" />
      <p className="text-sm text-slate-600">
        {suggestionCounts(data.counts) || "No suggestions yet. Run make suggest-links."} · AI cost so far $
        {data.cost_usd.toFixed(2)}
      </p>
      <div className="flex gap-1 border-b" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-3 py-1.5 text-sm ${tab === t.id ? "border-action font-medium text-action" : "border-transparent text-slate-600 hover:text-slate-900"}`}
          >
            {t.label} ({data.counts[t.id] ?? 0})
          </button>
        ))}
      </div>
      {error ? <p className="rounded border border-rose-200 bg-rose-50 p-2 text-sm text-rose-800">{error}</p> : null}
      {shown.length === 0 ? <p className="text-sm text-slate-500">Nothing here.</p> : null}
      <ul className="space-y-3">
        {shown.map((s) => (
          <li key={s.id} className="space-y-2 rounded border bg-white p-4">
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-500">Pull request · {s.pull_request_state ?? "unknown"}</p>
                <a href={s.pull_request_url ?? "#"} target="_blank" rel="noreferrer" className="font-medium text-action hover:underline">
                  {s.pull_request.split("/").pop()} {s.pull_request_title}
                </a>
                <blockquote className="mt-1 border-l-2 border-slate-200 pl-2 text-sm text-slate-700">“{s.pr_quote}”</blockquote>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-500">Suggested feature</p>
                <a href={`${ENH}/${s.feature_number}`} target="_blank" rel="noreferrer" className="font-medium text-action hover:underline">
                  #{s.feature_number} {s.feature_title}
                </a>
                <blockquote className="mt-1 border-l-2 border-slate-200 pl-2 text-sm text-slate-700">“{s.feature_quote}”</blockquote>
              </div>
            </div>
            <p className="text-xs text-slate-500">
              AI-suggested ({s.model}, {s.prompt_version}) · shortlist rank {s.shortlist_rank} of {s.shortlist_size} · both quotes
              checked word for word · counts only after a person confirms
            </p>
            {s.status === "suggested" ? (
              <div className="flex flex-wrap items-center gap-2">
                <input
                  aria-label="Note (optional)"
                  placeholder="Note (optional)"
                  value={notes[s.id] ?? ""}
                  onChange={(e) => setNotes((n) => ({ ...n, [s.id]: e.target.value }))}
                  className="min-w-48 flex-1 rounded border px-2 py-1 text-sm"
                />
                <button
                  disabled={busy !== null || !canAct}
                  onClick={() => decide(s, "confirm")}
                  className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  Confirm link
                </button>
                <button
                  disabled={busy !== null || !canAct}
                  onClick={() => decide(s, "reject")}
                  className="rounded border bg-white px-3 py-1.5 text-sm font-medium text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                >
                  Reject
                </button>
              </div>
            ) : (
              <p className="text-sm text-slate-600">
                {s.status === "confirmed" ? "Confirmed" : "Rejected"} by {s.decided_by?.replace(/^user:/, "")} on{" "}
                {s.decided_at ? formatUtc(s.decided_at) : "?"}
                {s.decision_note ? ` · “${s.decision_note}”` : ""}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
