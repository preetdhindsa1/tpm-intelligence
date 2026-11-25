import { featureLabel } from "@/lib/vocab";
// Dashboard panel: the groups of features tied to each other, stated cross-feature
// dependencies, and PRs waiting on an unmerged PR. Text, not a shrunken graph, so it
// stays readable in a third of the page; the map is on the Dependencies page.
import Link from "next/link";
import type { Dependencies } from "@/lib/api";
import { STATUS } from "@/lib/dashboard";
import { clusterName, depStats, PR_NUM, statedPairs } from "@/lib/dependencies";
import { releasePath } from "@/lib/routes";

const BORDER: Record<string, string> = { critical: STATUS.critical, warning: STATUS.warning };

export function DependencySummary({ project, release, data }: { project: string; release: string; data: Dependencies }) {
  const s = depStats(data);
  const byKey = new Map(data.features.map((f) => [f.key, f]));
  const page = releasePath(project, release, "/dependencies");
  const num = (k: string) => `#${byKey.get(k)?.number ?? "?"}`;
  return (
    <div className="flex h-full flex-col gap-3 text-sm">
      <p className="text-slate-700">
        <span className="text-2xl font-semibold text-slate-900">{s.coupled}</span> of {s.features} features are tied to another
        feature, in {s.clusters.length} group{s.clusters.length === 1 ? "" : "s"}. The other {s.features - s.coupled} stand alone.
      </p>

      {s.waiting > 0 && (
        <div className="rounded-md border px-3 py-2" style={{ borderColor: s.waitingOnClosed ? STATUS.critical : STATUS.warning }}>
          <p className="font-medium text-slate-800">
            {s.waitingOnClosed ? "⚠ " : ""}
            {s.waiting} open PR{s.waiting === 1 ? "" : "s"} waiting on an unmerged PR
          </p>
          <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
            {data.waiting.map((w) => (
              <li key={w.pr + w.waits_on}>
                {PR_NUM(w.pr)} ({w.features.map(num).join(", ")}) needs {PR_NUM(w.waits_on)},{" "}
                {w.waits_on_state === "closed" ? <span className="font-medium text-[#b02a2a]">closed without merging</span> : "still open"}
              </li>
            ))}
          </ul>
        </div>
      )}

      <ul className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {data.clusters.map((members, i) => {
          const feats = members.map((k) => byKey.get(k)!).filter(Boolean);
          const stated = statedPairs(members, data.couplings);
          return (
            <li key={i}>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {clusterName(feats)} · {feats.length} features
              </p>
              <div className="mt-1 flex flex-wrap gap-1">
                {feats.map((f) => (
                  <Link
                    key={f.key}
                    href={`${page}?feature=${f.number}`}
                    title={f.title}
                    className="rounded border-2 bg-white px-1.5 text-xs text-slate-700 hover:bg-slate-50"
                    style={{ borderColor: BORDER[f.severity ?? ""] ?? "#d6d4cc" }}
                  >
                    {featureLabel(f)}
                  </Link>
                ))}
              </div>
              {stated.length > 0 && (
                <p className="mt-1 text-xs text-[#b02a2a]">
                  Stated: {stated.map(([u, d]) => `${num(d)} depends on ${num(u)}`).join(" · ")}
                </p>
              )}
            </li>
          );
        })}
      </ul>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-2 text-xs text-slate-500">
        <span>
          Border: <span style={{ color: STATUS.critical }}>critical</span> / <span style={{ color: "#b88a0e" }}>warning</span> flag. Verified
          links only.
        </span>
        <Link href={page} className="font-medium text-action hover:underline">
          Explore the map →
        </Link>
      </div>
    </div>
  );
}
