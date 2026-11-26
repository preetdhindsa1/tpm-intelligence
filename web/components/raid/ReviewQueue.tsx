"use client";

// Waiting-for-review queue (docs/api/raid-contract.md). Suggested items only.
// The quote is the source's words and is never an input. Owners are roles.
import { useEffect, useState } from "react";
import { ApproverNote, useMe } from "@/components/Me";
import { confirmRaid, editRaid, rejectRaid, type RaidEdit, type RaidItem, type RaidList, type RaidSummary } from "@/lib/api-raid";
import { formatUtc } from "@/lib/format";
import { keyAction, linkLine, moveIndex, ownerText, progressText, reasonError, reviewedCount, TYPE_LABEL, typingTarget } from "@/lib/raid-review";

const FIELD = "min-h-11 rounded border border-slate-300 px-2 text-sm";

export function ReviewQueue({ queue, summary }: { queue: RaidList; summary: RaidSummary }) {
  const me = useMe();
  const canAct = me?.approver ?? false;
  const [items, setItems] = useState(queue.items);
  const [done, setDone] = useState(0);
  const [index, setIndex] = useState(0);
  const [mode, setMode] = useState<"edit" | "reject" | null>(null);
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [draft, setDraft] = useState<RaidEdit>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const current = items[index];

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement;
      if (typingTarget(el) || !keyAction(e.key)) return;
      e.preventDefault();
      const action = keyAction(e.key);
      if (action === "next" || action === "prev") {
        setIndex((i) => moveIndex(i, action === "next" ? 1 : -1, items.length));
        setMode(null);
        setDraft({});
        return;
      }
      if (!canAct || !current || busy) return;
      if (mode && (action === "confirm" || action === "edit")) return;
      if (action === "confirm") void run(() => confirmRaid(current.item_id, note.trim() || undefined));
      if (action === "edit") beginEdit();
      if (action === "reject") setMode("reject");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [canAct, current, busy, items.length, mode, note]);

  function beginEdit() {
    setDraft({});
    setMode("edit");
  }

  async function run(call: () => Promise<RaidItem>) {
    setBusy(true);
    setError(null);
    try {
      const saved = await call();
      setItems((rows) => {
        const next = rows.filter((row) => row.item_id !== saved.item_id);
        setIndex((i) => Math.min(i, Math.max(0, next.length - 1)));
        return next;
      });
      setDone((n) => n + 1);
      setMode(null);
      setDraft({});
      setNote("");
      setReason("");
      const id = saved.raid_id ? `Confirmed as ${saved.raid_id}` : "Saved, but the API did not return a RAID ID.";
      setNotice(saved.review === "rejected" ? "Rejected. No RAID ID is given to a rejected item." : id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The RAID API failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-heading text-2xl font-semibold">Waiting for review</h1>
        <p className="text-sm text-slate-600">{progressText(reviewedCount(summary) + done, items.length)}</p>
      </div>
      {queue.synthetic && <p className="inline-block rounded-full bg-warning-bg px-3 py-1 text-sm font-medium text-warning">Synthetic data</p>}
      <ApproverNote me={me} action="confirm, edit or reject RAID items" />
      <p className="text-sm text-slate-500">j and k move. c confirms, e edits, r rejects. Quotes stay as the meeting said them.</p>
      {notice && <p role="status" className="rounded-lg bg-healthy-bg px-4 py-3 text-sm font-medium text-healthy">{notice}</p>}
      {error && <p role="alert" className="rounded-lg bg-critical-bg px-4 py-3 text-sm text-critical">{error}</p>}
      {items.length === 0 ? (
        <p className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600">Nothing is waiting for review.</p>
      ) : (
        <ul className="space-y-3">
          {items.map((item, i) => (
            <li key={item.item_id} className={`rounded-2xl border border-dashed bg-warning-bg p-4 ${i === index ? "border-action" : "border-warning"}`}>
              <p className="text-xs font-semibold uppercase tracking-wide text-warning">Suggested · {TYPE_LABEL[item.type]}</p>
              <h2 className="mt-1 font-heading text-lg font-semibold">{item.title}</h2>
              <p className="mt-1 text-sm text-slate-600">Owner: {ownerText(item.owner)}</p>
              <blockquote className="mt-3 border-l-2 border-slate-300 pl-3 text-sm text-slate-800">{item.quote}</blockquote>
              <p className="mt-3 text-sm">
                {item.source.url ? (
                  <a href={item.source.url} className="font-medium text-action hover:underline">{item.source.title}</a>
                ) : (
                  <span>{item.source.title}</span>
                )}
                <span className="text-slate-500"> · {formatUtc(item.source.date)}</span>
                {item.source.synthetic ? <span className="text-warning"> · synthetic source</span> : null}
              </p>
              <p className="mt-1 text-sm text-slate-600">{linkLine(item.links)}</p>
              {item.merge_suggestion && (
                <p className="mt-2 text-sm text-slate-700">Might repeat item {item.merge_suggestion.into_item_id}. {item.merge_suggestion.reason}</p>
              )}
              {canAct && i === index && (
                <div className="mt-4 space-y-3">
                  {mode === "edit" && (
                    <div className="grid gap-2 sm:grid-cols-2">
                      <input aria-label="Title" className={FIELD} value={draft.title ?? item.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
                      <select aria-label="Type" className={FIELD} value={draft.type ?? item.type} onChange={(e) => setDraft({ ...draft, type: e.target.value as RaidEdit["type"] })}>
                        {Object.entries(TYPE_LABEL).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
                      </select>
                      <input aria-label="Owner role" className={FIELD} placeholder="Owner role" value={draft.owner ?? item.owner ?? ""} onChange={(e) => setDraft({ ...draft, owner: e.target.value })} />
                      <select aria-label="Status" className={FIELD} value={draft.status ?? item.status} onChange={(e) => setDraft({ ...draft, status: e.target.value as RaidEdit["status"] })}>
                        <option value="open">Open</option>
                        <option value="in_progress">In progress</option>
                        <option value="closed">Closed</option>
                        <option value="superseded">Superseded</option>
                      </select>
                    </div>
                  )}
                  {mode === "reject" && (
                    <input aria-label="Reason for rejecting" className={`${FIELD} w-full`} placeholder="Reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} />
                  )}
                  {mode !== "reject" && mode !== "edit" && (
                    <input aria-label="Note (optional)" className={`${FIELD} w-full`} placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
                  )}
                  <div className="flex flex-wrap gap-2">
                    <button type="button" disabled={busy} className="min-h-11 rounded-lg bg-action px-4 text-sm font-semibold text-white disabled:opacity-50" onClick={() => void run(() => confirmRaid(item.item_id, note.trim() || undefined))}>Confirm</button>
                    <button type="button" disabled={busy} className="min-h-11 rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold" onClick={() => (mode === "edit" ? void run(() => editRaid(item.item_id, filled(draft, item))) : beginEdit())}>Edit</button>
                    <button type="button" disabled={busy || (mode === "reject" && reasonError(reason) !== null)} className="min-h-11 rounded-lg border border-critical/40 px-4 text-sm font-semibold text-critical disabled:opacity-50" onClick={() => (mode === "reject" ? void run(() => rejectRaid(item.item_id, reason.trim())) : setMode("reject"))}>{mode === "reject" ? "Reject item" : "Reject"}</button>
                  </div>
                  {mode === "reject" && reasonError(reason) && <p className="text-sm text-critical">{reasonError(reason)}</p>}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Fields the person actually changed. The quote is never one of them. */
function filled(draft: RaidEdit, item: RaidItem): RaidEdit {
  const out: RaidEdit = {};
  if (draft.title && draft.title !== item.title) out.title = draft.title;
  if (draft.type && draft.type !== item.type) out.type = draft.type;
  if (draft.owner && draft.owner.trim() && draft.owner !== item.owner) out.owner = draft.owner.trim();
  if (draft.status && draft.status !== item.status) out.status = draft.status;
  return out;
}
