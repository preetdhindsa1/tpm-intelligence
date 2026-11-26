"use client";

import { useState } from "react";
import type { RaidList, RaidSummary } from "@/lib/api-raid";
import { ReviewQueue } from "./ReviewQueue";
import { Tracker } from "./Tracker";

export function RaidTabs({ queue, summary, tracker }: { queue: RaidList; summary: RaidSummary; tracker: RaidList }) {
  const [tab, setTab] = useState<"queue" | "tracker">("queue");
  const tabs = [
    { id: "queue" as const, label: "Waiting for review" },
    { id: "tracker" as const, label: "Tracker" },
  ];
  return (
    <div className="space-y-4">
      <div role="tablist" aria-label="RAID" className="flex gap-5 border-b border-slate-200">
        {tabs.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)} className={`-mb-px min-h-11 border-b-2 px-1 text-sm ${tab === t.id ? "border-action font-medium text-action" : "border-transparent text-slate-600"}`}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "queue" ? <ReviewQueue queue={queue} summary={summary} /> : <Tracker list={tracker} />}
    </div>
  );
}
