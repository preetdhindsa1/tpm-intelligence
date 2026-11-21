import Link from "next/link";
import { FlagChips } from "@/components/Flags";
import { LiveRefresh } from "@/components/LiveRefresh";
import { OddsCell } from "@/components/Odds";
import { api } from "@/lib/api";
import { formatUtc } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function ReleasePage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const data = await api.features(name);
  const r = data.release;
  const current = data.features.filter((f) => f.in_release);
  const removed = data.features.filter((f) => !f.in_release);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Kubernetes {r.name} release health</h1>
          <p className="text-sm text-slate-600">
            Code Freeze {r.code_freeze_at ? formatUtc(r.code_freeze_at) : "unknown"} · {r.features_in_release} features in
            the release now · {r.features_ever_in_release} ever · data as of {formatUtc(r.as_of)}
          </p>
        </div>
        <LiveRefresh release={name} />
      </div>

      {!data.validation.validated ? (
        <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <strong>Odds are not validated.</strong> {data.validation.reason}. Read them next to the base rate shown in each
          cell. Flags and dates are computed facts and are not affected.
        </div>
      ) : null}

      <FeatureTable title={`In the release (${current.length})`} rows={current} release={name} />
      {removed.length ? <FeatureTable title={`Removed from the release (${removed.length})`} rows={removed} release={name} /> : null}
    </div>
  );
}

function FeatureTable({ title, rows, release }: { title: string; rows: Awaited<ReturnType<typeof api.features>>["features"]; release: string }) {
  return (
    <section>
      <h2 className="mb-2 text-lg font-medium">{title}</h2>
      <div className="overflow-x-auto rounded border bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-100 text-left text-xs uppercase text-slate-600">
            <tr>
              <th className="px-3 py-2">Feature</th>
              <th className="px-3 py-2">SIGs</th>
              <th className="px-3 py-2">Stage</th>
              <th className="px-3 py-2">Odds by Code Freeze</th>
              <th className="px-3 py-2">Flags</th>
              <th className="px-3 py-2">Linked PRs</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((f) => (
              <tr key={f.key} className="align-top">
                <td className="px-3 py-2">
                  <Link className="font-medium text-indigo-700 hover:underline" href={`/releases/${release}/features/${f.number}`}>
                    #{f.number}
                  </Link>{" "}
                  {f.title}
                  {!f.tracked && f.in_release ? <span className="ml-1 text-xs text-slate-500">(not tracked)</span> : null}
                </td>
                <td className="px-3 py-2 text-xs text-slate-600">{f.teams.map((t) => t.replace("sig/", "")).join(", ")}</td>
                <td className="px-3 py-2 text-xs">{f.stage ?? "—"}</td>
                <td className="px-3 py-2"><OddsCell odds={f.odds} /></td>
                <td className="px-3 py-2"><FlagChips flags={f.flags} /></td>
                <td className="px-3 py-2 text-xs">
                  {f.prs_merged}/{f.prs_total} merged
                  {f.prs_open ? ` · ${f.prs_open} open` : ""}
                  {f.suggested_prs ? <div className="text-slate-500">{f.suggested_prs} suggested (unconfirmed)</div> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
