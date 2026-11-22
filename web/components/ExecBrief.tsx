// The newest approved executive update, else the newest draft, clearly labelled.
// Every line shown was verified by the fact checker before it was stored (ADR-0010).
import Link from "next/link";
import { SECTION_TITLES, type ExecUpdate } from "@/lib/api";
import { formatUtc } from "@/lib/format";
import { releasePath } from "@/lib/routes";

export function ExecBrief({ project, release, update }: { project: string; release: string; update: ExecUpdate | null }) {
  if (!update) {
    return (
      <p className="text-sm text-slate-500">
        No update drafted yet.{" "}
        <Link href={releasePath(project, release, "/update")} className="text-indigo-700 hover:underline">
          Draft one →
        </Link>
      </p>
    );
  }
  const approved = update.status === "approved";
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {approved ? (
          <span className="rounded bg-emerald-50 px-1.5 py-0.5 font-medium text-emerald-800">
            ✓ Approved by {update.decided_by?.replace("user:", "")} · {update.decided_at ? formatUtc(update.decided_at) : ""}
          </span>
        ) : (
          <span className="rounded bg-amber-50 px-1.5 py-0.5 font-medium text-amber-900">Draft #{update.id}, awaiting TPM approval</span>
        )}
        {update.stale && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">facts changed since drafting</span>}
      </div>
      {Object.entries(SECTION_TITLES).map(([key, title]) => {
        const claims = update.sections[key] ?? [];
        if (!claims.length) return null;
        return (
          <div key={key}>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
            <ul className="mt-1 space-y-1">
              {claims.slice(0, 4).map((c) => (
                <li key={c.text} className="flex gap-1.5 text-slate-700">
                  <span className="mt-0.5 text-[#0ca30c]" aria-label="verified">
                    ✓
                  </span>
                  <span>{c.text}</span>
                </li>
              ))}
              {claims.length > 4 && <li className="pl-5 text-xs text-slate-500">and {claims.length - 4} more</li>}
            </ul>
          </div>
        );
      })}
      <p className="border-t pt-2 text-xs text-slate-500">
        ✓ = checked against the data by the fact checker. {update.claims_removed} claim{update.claims_removed === 1 ? "" : "s"} removed. Drafted{" "}
        {formatUtc(update.created_at)} by AI; nothing is sent without approval.{" "}
        <Link href={releasePath(project, release, "/update")} className="font-medium text-indigo-700 hover:underline">
          Open report →
        </Link>
      </p>
    </div>
  );
}
