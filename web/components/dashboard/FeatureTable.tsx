import Link from "next/link";
import type { FeatureRow } from "@/lib/api";
import { FlagChips } from "@/components/Flags";
import { OddsCell } from "@/components/Odds";

export function FeatureTable({
  title,
  rows,
  release,
}: {
  title: string;
  rows: FeatureRow[];
  release: string;
}) {
  return (
    <div className="tpm-card overflow-hidden">
      <h2 className="border-b border-[var(--tpm-line)] px-4 py-3 text-sm font-semibold">{title}</h2>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-[var(--tpm-sidebar)] text-left text-[11px] uppercase text-[var(--tpm-muted)]">
            <tr>
              <th className="px-3 py-2">Feature</th>
              <th className="px-3 py-2">SIGs</th>
              <th className="px-3 py-2">Stage</th>
              <th className="px-3 py-2">Odds</th>
              <th className="px-3 py-2">Flags</th>
              <th className="px-3 py-2">PRs</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--tpm-line)]">
            {rows.map((f) => (
              <tr key={f.key} className="align-top">
                <td className="px-3 py-2">
                  <Link
                    className="font-medium text-[var(--tpm-accent)] hover:underline"
                    href={`/releases/${release}/features/${f.number}`}
                  >
                    #{f.number}
                  </Link>{" "}
                  {f.title}
                  {!f.tracked && f.in_release ? (
                    <span className="ml-1 text-xs text-[var(--tpm-muted)]">(not tracked)</span>
                  ) : null}
                </td>
                <td className="px-3 py-2 text-xs text-[var(--tpm-muted)]">
                  {f.teams.map((t) => t.replace("sig/", "")).join(", ")}
                </td>
                <td className="px-3 py-2 text-xs">{f.stage ?? "—"}</td>
                <td className="px-3 py-2">
                  <OddsCell odds={f.odds} />
                </td>
                <td className="px-3 py-2">
                  <FlagChips flags={f.flags} />
                </td>
                <td className="px-3 py-2 text-xs">
                  {f.prs_merged}/{f.prs_total} merged
                  {f.prs_open ? ` · ${f.prs_open} open` : ""}
                  {f.suggested_prs ? (
                    <div className="text-[var(--tpm-muted)]">{f.suggested_prs} suggested</div>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
