import type { TimelineEntry } from "@/lib/api";
import { formatUtc, timelineLabel } from "@/lib/format";

const MARKER: Record<string, string> = {
  code_freeze: "bg-slate-900",
  enhancements_freeze: "bg-slate-500",
  release: "bg-slate-500",
  removed_from_release: "bg-rose-600",
  untracked: "bg-rose-400",
  added_to_release: "bg-emerald-600",
  tracked: "bg-emerald-400",
  pr_merged: "bg-indigo-600",
  pr_opened: "bg-indigo-300",
  pr_closed: "bg-slate-300",
};

/** Vertical timeline of dated facts; freeze dates are drawn as solid milestones. */
export function Timeline({ entries }: { entries: TimelineEntry[] }) {
  return (
    <ol className="relative ml-2 border-l border-slate-200">
      {entries.map((e, i) => {
        const milestone = e.kind.endsWith("freeze") || e.kind === "release";
        return (
          <li key={`${e.at}-${e.kind}-${e.ref ?? i}`} className={`ml-4 pb-3 ${milestone ? "font-semibold" : ""}`}>
            <span className={`absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full ${MARKER[e.kind] ?? "bg-slate-300"}`} />
            <div className="text-xs text-slate-500">{formatUtc(e.at)}</div>
            <div className="text-sm">
              {timelineLabel(e.kind)}
              {e.ref ? (
                <a className="ml-1 text-indigo-700 underline" href={`https://github.com/${e.ref.replace("#", "/pull/")}`}>
                  {e.ref.split("/").pop()}
                </a>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
