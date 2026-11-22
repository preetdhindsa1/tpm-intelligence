"use client";

import { useCallback, useEffect, useState } from "react";
import { SECTION_TITLES, updatesRequest, type ExecUpdate, type VerifiedClaim } from "@/lib/api";
import { ApproverNote, useMe } from "@/components/Me";
import { formatUtc, refLabel } from "@/lib/format";

const ORDER = ["summary", "at_risk", "removed", "asks"];

export function ExecUpdatePanel({ release }: { release: string }) {
  const me = useMe();
  const canAct = me?.approver ?? false;
  const [updates, setUpdates] = useState<ExecUpdate[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    const list = await updatesRequest<ExecUpdate[]>(`/releases/${release}/updates`);
    setUpdates(list);
    setSelected((s) => s ?? list[0]?.id ?? null);
  }, [release]);

  useEffect(() => {
    let cancelled = false;
    updatesRequest<ExecUpdate[]>(`/releases/${release}/updates`)
      .then((list) => {
        if (cancelled) return;
        setUpdates(list);
        setSelected((s) => s ?? list[0]?.id ?? null);
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoaded(true));
    return () => {
      cancelled = true;
    };
  }, [release]);

  async function run<T>(label: string, fn: () => Promise<T>) {
    setBusy(label);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function draft() {
    const u = await run("Drafting (about 30 seconds)…", () =>
      updatesRequest<ExecUpdate>(`/releases/${release}/updates`, { method: "POST" }),
    );
    if (u) {
      await load();
      setSelected(u.id);
    }
  }

  const current = updates.find((u) => u.id === selected) ?? null;
  const replace = (u: ExecUpdate) => setUpdates((list) => list.map((x) => (x.id === u.id ? u : x)));

  return (
    <div className="space-y-4">
      <ApproverNote me={me} action="draft, edit or approve updates" />
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={draft}
          disabled={busy !== null || !canAct}
          className="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          Draft update
        </button>
        {updates.length ? (
          <select
            className="rounded border bg-white px-2 py-1 text-sm"
            value={selected ?? ""}
            onChange={(e) => setSelected(Number(e.target.value))}
            aria-label="Choose an update"
          >
            {updates.map((u) => (
              <option key={u.id} value={u.id}>
                #{u.id} · {u.status} · {formatUtc(u.created_at)}
              </option>
            ))}
          </select>
        ) : null}
        {busy ? <span className="text-sm text-slate-500" aria-live="polite">{busy}</span> : null}
      </div>
      {error ? <p className="rounded border border-rose-200 bg-rose-50 p-2 text-sm text-rose-800">{error}</p> : null}
      {!loaded ? <p className="text-sm text-slate-500">Loading updates…</p> : null}
      {loaded && !current && !busy && !error ? <p className="text-sm text-slate-500">No updates yet.</p> : null}
      {current ? <UpdateView key={current.id} update={current} release={release} onChange={replace} run={run} canAct={canAct} /> : null}
    </div>
  );
}

type Runner = <T>(label: string, fn: () => Promise<T>) => Promise<T | undefined>;

function UpdateView({
  update,
  release,
  onChange,
  run,
  canAct,
}: {
  update: ExecUpdate;
  release: string;
  onChange: (u: ExecUpdate) => void;
  run: Runner;
  canAct: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draftSections, setDraftSections] = useState<Record<string, VerifiedClaim[]>>(update.sections);
  const [ackWarnings, setAckWarnings] = useState(false);
  const [ackStale, setAckStale] = useState(false);
  const [note, setNote] = useState("");
  const [copied, setCopied] = useState(false);
  const h = update.header;
  const base = `/releases/${release}/updates/${update.id}`;

  async function save() {
    const u = await run("Saving and re-checking…", () =>
      updatesRequest<ExecUpdate>(base, { method: "PATCH", body: JSON.stringify({ sections: draftSections }) }),
    );
    if (u) {
      onChange(u);
      setEditing(false);
    }
  }

  async function decide(kind: "approve" | "reject") {
    const u = await run(kind === "approve" ? "Approving…" : "Rejecting…", () =>
      updatesRequest<ExecUpdate>(`${base}/${kind}`, {
        method: "POST",
        body: JSON.stringify({ acknowledge_warnings: ackWarnings, acknowledge_stale: ackStale, note: note || null }),
      }),
    );
    if (u) onChange(u);
  }

  const sections = editing ? draftSections : update.sections;
  const badge = {
    draft: "bg-amber-100 text-amber-900",
    approved: "bg-emerald-100 text-emerald-900",
    rejected: "bg-slate-200 text-slate-700",
  }[update.status];

  return (
    <article className="space-y-4 rounded border bg-white p-5">
      <header className="space-y-1 border-b pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold">{h.release} release update</h2>
          <span className={`rounded px-2 py-0.5 text-xs font-medium ${badge}`}>{update.status}</span>
          {update.edited ? <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">edited by TPM</span> : null}
        </div>
        <p className="text-sm text-slate-600">
          Data as of {h.data_as_of ? formatUtc(h.data_as_of) : "?"} · Code Freeze {h.code_freeze_at ? formatUtc(h.code_freeze_at) : "?"} ·
          Release {h.release_at ? formatUtc(h.release_at) : "?"}
        </p>
        <p className="text-sm text-slate-600">
          {h.features_in_release} features in the release · {h.features_at_risk} at risk · {h.features_removed} removed
          {!h.odds_validated ? " · odds not validated" : ""}
        </p>
      </header>

      {update.stale && update.status === "draft" ? (
        <p className="rounded bg-amber-50 p-2 text-sm text-amber-900">
          The facts changed meaningfully since this draft. Draft a new update, or acknowledge below to approve anyway.
        </p>
      ) : null}

      {ORDER.map((name) =>
        (sections[name] ?? []).length ? (
          <section key={name}>
            <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-slate-500">{SECTION_TITLES[name]}</h3>
            <ul className="space-y-2">
              {(sections[name] ?? []).map((c, i) => (
                <li key={`${name}-${i}`} className="text-sm">
                  {editing ? (
                    <div className="flex gap-2">
                      <textarea
                        className="w-full rounded border p-1 text-sm"
                        value={c.text}
                        aria-label={`Edit claim ${i + 1} in ${SECTION_TITLES[name]}`}
                        onChange={(e) =>
                          setDraftSections((s) => ({
                            ...s,
                            [name]: s[name].map((x, j) => (j === i ? { ...x, text: e.target.value } : x)),
                          }))
                        }
                      />
                      <button
                        className="h-fit rounded border px-2 py-1 text-xs text-rose-700 hover:bg-rose-50"
                        onClick={() => setDraftSections((s) => ({ ...s, [name]: s[name].filter((_, j) => j !== i) }))}
                      >
                        Remove
                      </button>
                    </div>
                  ) : (
                    <>
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
                    </>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ) : null,
      )}

      {update.warnings.length ? (
        <div className="rounded border border-amber-300 bg-amber-50 p-2 text-sm text-amber-900">
          <strong>{update.warnings.length} edited claim(s) fail the fact check:</strong>
          <ul className="mt-1 list-disc pl-5">
            {update.warnings.map((w) => (
              <li key={w.text}>{w.text} ({w.reason.replaceAll("_", " ")}{w.detail ? `: ${w.detail}` : ""})</li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="text-xs text-slate-500">
        {update.word_count} words · {update.claims_removed} claim(s) removed by the fact checker
        {update.trimmed_for_length ? ` · ${update.trimmed_for_length} dropped for length` : ""} · {update.model} ·{" "}
        {update.prompt_version} · ${update.cost_usd.toFixed(4)}
        {update.attempts > 1 ? ` · ${update.attempts} attempts` : ""}
      </p>

      {update.status === "draft" ? (
        <div className="space-y-2 border-t pt-3">
          <div className="flex flex-wrap gap-2">
            {editing ? (
              <>
                <button onClick={save} className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-900">Save and re-check</button>
                <button onClick={() => { setDraftSections(update.sections); setEditing(false); }} className="rounded border px-3 py-1.5 text-sm">Cancel</button>
              </>
            ) : (
              <button onClick={() => setEditing(true)} disabled={!canAct} className="rounded border px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50">Edit</button>
            )}
          </div>
          {!editing ? (
            <div className="space-y-2">
              {update.warnings.length ? (
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={ackWarnings} onChange={(e) => setAckWarnings(e.target.checked)} />
                  I accept the edited claims that fail the fact check.
                </label>
              ) : null}
              {update.stale ? (
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={ackStale} onChange={(e) => setAckStale(e.target.checked)} />
                  I accept that the facts changed since this draft.
                </label>
              ) : null}
              <input
                className="w-full rounded border px-2 py-1 text-sm"
                placeholder="Note (optional)"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                aria-label="Decision note"
              />
              <div className="flex gap-2">
                <button onClick={() => decide("approve")} disabled={!canAct} className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50">Approve</button>
                <button onClick={() => decide("reject")} disabled={!canAct} className="rounded border px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50">Reject</button>
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="space-y-2 border-t pt-3">
          <p className="text-sm text-slate-600">
            {update.status === "approved" ? "Approved" : "Rejected"} by {update.decided_by} on{" "}
            {update.decided_at ? formatUtc(update.decided_at) : "?"}
            {update.approved_with_warnings ? " · with fact-check warnings" : ""}
            {update.approved_while_stale ? " · while facts had changed" : ""}
            {update.decision_note ? ` · “${update.decision_note}”` : ""}
          </p>
          {update.status === "approved" ? (
            <>
              <button
                onClick={async () => {
                  await navigator.clipboard.writeText(update.markdown);
                  setCopied(true);
                }}
                className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-900"
              >
                {copied ? "Copied" : "Copy as Markdown"}
              </button>
              <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs">{update.markdown}</pre>
            </>
          ) : null}
        </div>
      )}
    </article>
  );
}
