"use client";

// Confirmed and edited RAID items. History is oldest first; the actor is a role.
import { useState } from "react";
import { browserGet } from "@/lib/api-http";
import type { RaidHistory, RaidItem, RaidList } from "@/lib/api-raid";
import { formatUtc } from "@/lib/format";
import { raidHtml, raidMarkdown } from "@/lib/raid-copy";
import { actorRole, EMPTY_FILTER, oldestFirst, trackerRows, type TrackerFilter } from "@/lib/raid-tracker";
import { ownerText, TYPE_LABEL } from "@/lib/raid-review";

const STATUS: Record<string, string> = { open: "Open", in_progress: "In progress", closed: "Closed", superseded: "Superseded" };
const FIELD = "min-h-11 rounded border border-slate-300 bg-white px-2 text-sm";

export function Tracker({ list }: { list: RaidList }) {
  const [filter, setFilter] = useState<TrackerFilter>(EMPTY_FILTER);
  const [openId, setOpenId] = useState<number | null>(null);
  const [history, setHistory] = useState<RaidHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const rows = trackerRows(list.items, filter);
  const workstreams = [...new Set(list.items.map((i) => i.workstream))].sort();

  async function copy(kind: string, text: string) {
    await navigator.clipboard.writeText(text);
    setCopied(`Copied as ${kind}. Nothing was sent.`);
  }

  async function toggle(item: RaidItem) {
    if (openId === item.item_id) {
      setOpenId(null);
      return;
    }
    setOpenId(item.item_id);
    setHistory(null);
    setError(null);
    try {
      setHistory(await browserGet<RaidHistory>(`/raid/${item.item_id}/history`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "History could not be loaded");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-heading text-2xl font-semibold">Tracker</h1>
        {list.synthetic && <p className="rounded-full bg-warning-bg px-3 py-1 text-sm font-medium text-warning">Synthetic data</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <select aria-label="Type" className={FIELD} value={filter.type} onChange={(e) => setFilter({ ...filter, type: e.target.value })}>
          <option value="">All types</option>
          {Object.entries(TYPE_LABEL).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select>
        <select aria-label="Status" className={FIELD} value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
          <option value="">All statuses</option>
          {Object.entries(STATUS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select>
        <select aria-label="Workstream" className={FIELD} value={filter.workstream} onChange={(e) => setFilter({ ...filter, workstream: e.target.value })}>
          <option value="">All workstreams</option>
          {workstreams.map((w) => <option key={w} value={w}>{w}</option>)}
        </select>
        <button type="button" className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm font-semibold" onClick={() => void copy("Markdown", raidMarkdown(rows))}>Copy as Markdown</button>
        <button type="button" className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm font-semibold" onClick={() => void copy("HTML", raidHtml(rows))}>Copy as HTML</button>
      </div>
      {copied && <p role="status" className="text-sm text-slate-600">{copied}</p>}
      {rows.length === 0 ? (
        <p className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600">No confirmed items match these filters.</p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white">
          {rows.map((item) => (
            <li key={item.item_id}>
              <button type="button" className="flex w-full flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-3 text-left hover:bg-slate-50" onClick={() => void toggle(item)} aria-expanded={openId === item.item_id}>
                <span className="font-mono text-sm font-semibold text-action">{item.raid_id}</span>
                <span className="font-medium text-slate-900">{item.title}</span>
                <span className="text-sm text-slate-600">{ownerText(item.owner)} · {STATUS[item.status] ?? item.status}</span>
                <span className="ml-auto text-sm text-slate-500">Last change {formatUtc(item.updated_at)}</span>
              </button>
              {openId === item.item_id && (
                <div className="border-t border-slate-100 px-4 py-3">
                  <blockquote className="border-l-2 border-slate-300 pl-3 text-sm text-slate-800">{item.quote}</blockquote>
                  {error && <p role="alert" className="mt-2 text-sm text-critical">{error}</p>}
                  {history && (
                    <ol className="mt-3 space-y-1 text-sm text-slate-700">
                      {oldestFirst(history.history).map((entry) => (
                        <li key={`${entry.at}-${entry.action}`}>{formatUtc(entry.at)} · {actorRole(entry.actor)} · {entry.action}{entry.reason ? ` · ${entry.reason}` : ""}</li>
                      ))}
                    </ol>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
