"use client";

import { useState } from "react";
import {
  MEMBER_TEXT, METRIC_NAME, NEXT_RULES, STAGE_TEXT, metricValue, ruleValue, stageDetail, stageValue, statusTone,
  type Pod,
} from "@/lib/api-pdlc";

export function PdlcView({ pod, asOf, total, merged }: { pod: Pod; asOf: string; total: number; merged: number }) {
  const [si, setSi] = useState(() => Math.max(0, pod.flow.findIndex((s) => s.stage === "cross_review")));
  const [ri, setRi] = useState(0);
  const cur = pod.flow[si];
  return (
    <div className="space-y-6">
      <section className="-mx-6 -mt-6 bg-ink px-6 pb-10 pt-8 text-white">
        <div className="mx-auto max-w-[1400px]">
        <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-indigo-300">AI-native PDLC</span>
          <span aria-hidden className="text-slate-500">/</span>
          <span className="rounded-md border border-white/20 px-2.5 py-1 text-white">Pod: Program Intelligence repo</span>
          <span className="text-slate-300">Real pull requests · as of {asOf}</span>
        </nav>
        <h1 className="mt-4 font-heading text-4xl font-bold tracking-tight">How the pod builds, checks and ships</h1>
        <p className="mt-2 max-w-3xl text-slate-200">
          In a pod of 1 human, 2 AI agents and a bot, code is cheap and the human&apos;s attention is the only scarce
          thing. Velocity is merged, kept and released changes, never PRs opened.
        </p>
        <ul className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {pod.members.map((m) => {
            const t = MEMBER_TEXT[m.lane] ?? { name: m.lane, does: "", never: "" };
            return (
              <li key={m.lane} className="rounded-xl border border-slate-700 bg-[#111833] p-4">
                <div className="flex justify-between gap-2 text-xs uppercase tracking-wide text-slate-300">
                  <span>{t.name}</span><b className="text-white">{m.opened} PRs</b>
                </div>
                <p className="mt-2 font-medium">{t.does}</p>
                <p className="mt-1 text-sm text-slate-300">
                  {m.merged} merged · {m.closed_unmerged} closed unmerged · {m.open} open
                  {m.median_minutes_to_merge !== null ? ` · ${m.median_minutes_to_merge} min median to merge` : ""}
                </p>
                <p className="mt-1 text-sm text-slate-300">{t.never}</p>
              </li>
            );
          })}
        </ul>
        <p className="mt-3 text-sm text-slate-300">
          {total} pull requests in this repository&apos;s whole history, {merged} merged, {pod.no_lane} with no lane. The
          pod rules started on 24 Nov 2026, so older PRs show as breaking them.
        </p>
        </div>
      </section>

      <section className="rounded-2xl border bg-white p-6">
        <h2 className="font-heading text-xl font-semibold">The pod flow: where work moves, and where it skips a step</h2>
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7" role="group" aria-label="Pod flow stages">
          {pod.flow.map((s, k) => (
            <button key={s.stage} type="button" aria-pressed={k === si} onClick={() => setSi(k)}
              className={`flex min-h-24 flex-col items-start gap-1 rounded-xl border p-3 text-left ${k === si ? "border-action bg-indigo-50" : "bg-white"}`}>
              <span className="text-xs text-slate-600">{k + 1} · {s.rules}</span>
              <span className="font-medium">{STAGE_TEXT[s.stage]?.name ?? s.stage}</span>
              <span className={`rounded px-1.5 text-sm font-medium ${statusTone(s.status)}`}>{stageValue(s)}</span>
            </button>
          ))}
        </div>
        {cur && (
          <div className="mt-4 grid gap-4 md:grid-cols-3">
            <div className="rounded-xl bg-slate-50 p-4 md:col-span-2" aria-live="polite">
              <p className="text-sm text-slate-600">{STAGE_TEXT[cur.stage]?.name} · {cur.rules} · {cur.status.replace("_", " ")}</p>
              <p className="mt-1 text-sm leading-6 text-slate-800">{stageDetail(cur) || "No detail."}</p>
            </div>
            <div className="rounded-xl bg-indigo-50 p-4">
              <p className="text-sm text-indigo-800">The pod rule</p>
              <p className="mt-1 text-sm leading-6 text-indigo-950">{STAGE_TEXT[cur.stage]?.rule}</p>
            </div>
          </div>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border bg-white p-6">
          <h2 className="font-heading text-lg font-semibold">Pod metrics vs starting targets</h2>
          <p className="text-sm text-slate-600">Medians only from 5+ merged PRs in a lane (R22).</p>
          <table className="mt-3 w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr><th className="py-1">Metric</th><th>Target</th><th>Now</th></tr>
            </thead>
            <tbody>
              {pod.metrics.map((m) => (
                <tr key={m.metric} className="border-t align-top">
                  <td className="py-2 pr-2">{METRIC_NAME[m.metric] ?? m.metric}</td>
                  <td className="pr-2">{m.target}</td>
                  <td className={m.value === null ? "text-slate-600" : "font-medium"}>{metricValue(m)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="rounded-2xl border bg-white p-6">
          <h2 className="font-heading text-lg font-semibold">Pod rules, checked against real PRs</h2>
          <p className="text-sm text-slate-600">A rule is kept only if the data says it helps (R23).</p>
          <ul className="mt-3 space-y-2 text-sm">
            {pod.rules.map((r) => (
              <li key={r.rule} className={`flex justify-between gap-3 rounded-lg px-3 py-2 ${statusTone(r.status)}`}>
                <span><b>{r.rule}</b> {r.title}</span><span className="font-medium">{ruleValue(r)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="rounded-2xl bg-ink p-6 text-white">
        <h2 className="font-heading text-xl font-semibold">Turn on the next pod rule, then measure what it costs</h2>
        <p className="mt-1 text-sm text-slate-300">Each rule is enforced by branch rules, labels or a workflow. The platform shows the change in flow.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4" role="group" aria-label="Next pod rule">
          {NEXT_RULES.map((r, k) => (
            <button key={r.title} type="button" aria-pressed={k === ri} onClick={() => setRi(k)}
              className={`flex min-h-11 flex-col gap-1 rounded-xl border p-4 text-left ${k === ri ? "border-indigo-300 bg-indigo-900" : "border-slate-700 bg-[#111833]"}`}>
              <span className="font-medium">{r.title}</span><span className="text-sm text-slate-300">{r.body}</span>
            </button>
          ))}
        </div>
        <p className="mt-4 rounded-xl border border-slate-700 bg-[#111833] p-4 text-sm" aria-live="polite">{NEXT_RULES[ri].effect}</p>
        <p className="mt-3 text-xs text-slate-300">This page uses real pull requests only. What-ifs live in the Decision Studio and are labeled as model outputs.</p>
      </section>
    </div>
  );
}
