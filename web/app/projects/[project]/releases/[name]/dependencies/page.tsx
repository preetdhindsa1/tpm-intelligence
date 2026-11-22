import Link from "next/link";
import { DependencyMap } from "@/components/DependencyMap";
import { api, type DepFeature } from "@/lib/api";
import { OUTCOME_META, STATUS } from "@/lib/dashboard";
import { depStats, PR_NUM, shortSig } from "@/lib/dependencies";
import { formatUtc } from "@/lib/format";
import { releaseFromParams } from "@/lib/release-page";
import { releasePath } from "@/lib/routes";

export const dynamic = "force-dynamic";

const prUrl = (key: string) => `https://github.com/${key.replace("#", "/pull/")}`;

export default async function DependenciesPage({
  params,
  searchParams,
}: {
  params: Promise<{ project: string; name: string }>;
  searchParams: Promise<{ removed?: string; feature?: string }>;
}) {
  const release = await releaseFromParams(params);
  const name = release.name;
  const project = release.project;
  const sp = await searchParams;
  const includeRemoved = sp.removed === "1";
  const data = await api.dependencies(name, includeRemoved);
  const s = depStats(data);
  const byKey = new Map(data.features.map((f) => [f.key, f]));
  const initial = sp.feature ? (data.features.find((f) => String(f.number) === sp.feature)?.key ?? null) : null;
  const standalone = data.features.filter((f) => f.cluster === null);
  const maxPair = Math.max(1, ...data.sig_pairs.map((p) => p.features));
  const toggle = `${releasePath(project, name, "/dependencies")}${includeRemoved ? "" : "?removed=1"}`;

  const tiles: { label: string; value: string; note: string; tone?: string }[] = [
    { label: "Features tied to another feature", value: `${s.coupled} of ${s.features}`, note: "share PRs or state a dependency" },
    { label: "Groups of tied features", value: `${s.clusters.length}`, note: s.clusters.length ? `sizes ${s.clusters.join(", ")}` : "none" },
    { label: "Stated cross-feature dependencies", value: `${s.stated}`, note: "a PR says it depends on another feature's PR" },
    {
      label: "Open PRs waiting on an unmerged PR",
      value: `${s.waiting}`,
      note: s.waitingOnClosed ? `${s.waitingOnClosed} on a PR closed without merging` : "none on a closed PR",
      tone: s.waitingOnClosed ? STATUS.critical : undefined,
    },
    { label: "Features spanning 2+ SIGs", value: `${s.multiSig}`, note: "need coordination between SIGs" },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">
            Dependencies · {release.display_name || release.project} {name}
          </h1>
          <p className="max-w-4xl text-sm text-slate-600">
            How features depend on each other, from verified PR links and &quot;depends on&quot; statements in PR text. KEPs have no
            machine-readable dependency field, so this shows what the data says and nothing deeper. Data as of {formatUtc(data.as_of)}.
          </p>
        </div>
        <Link href={toggle} className="rounded-md border bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50">
          {includeRemoved ? "Hide removed features" : "Include removed features"}
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-lg border bg-white px-4 py-3 shadow-sm">
            <p className="text-xs text-slate-500">{t.label}</p>
            <p className="text-2xl font-semibold text-slate-900">{t.value}</p>
            <p className="text-xs" style={{ color: t.tone ?? "#64748b" }}>
              {t.tone ? "⚠ " : ""}
              {t.note}
            </p>
          </div>
        ))}
      </div>

      <section className="rounded-lg border bg-white p-4 shadow-sm">
        <h2 className="font-semibold text-slate-800">Feature dependency map</h2>
        <p className="mb-3 text-xs text-slate-500">
          Only features tied to another feature are drawn, grouped by what ties them; the {standalone.length} stand-alone features are
          listed below. Shared PRs mean shared code, not proof that one blocks the other.
        </p>
        <div className="h-[760px]">
          <DependencyMap project={project} release={name} data={data} initialSelected={initial} />
        </div>
      </section>

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <section className="rounded-lg border bg-white p-4 shadow-sm">
          <h2 className="font-semibold text-slate-800">Open PRs waiting on an unmerged PR</h2>
          <p className="mb-3 text-xs text-slate-500">The PR text says it depends on another PR that has not merged.</p>
          {data.waiting.length ? (
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Open PR</th>
                  <th className="py-1 pr-2">Waits on</th>
                  <th className="py-1">Feature</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {data.waiting.map((w) => (
                  <tr key={w.pr + w.waits_on} className="align-top">
                    <td className="py-2 pr-2">
                      <a href={prUrl(w.pr)} className="font-medium text-indigo-700 hover:underline" target="_blank" rel="noopener">
                        {PR_NUM(w.pr)}
                      </a>
                      <div className="text-xs text-slate-500">{w.pr_title}</div>
                    </td>
                    <td className="py-2 pr-2">
                      <a href={prUrl(w.waits_on)} className="font-medium text-indigo-700 hover:underline" target="_blank" rel="noopener">
                        {PR_NUM(w.waits_on)}
                      </a>{" "}
                      {w.waits_on_state === "closed" ? (
                        <span className="rounded bg-[#d03b3b] px-1 text-[10px] font-medium text-white">⚠ closed without merging</span>
                      ) : (
                        <span className="rounded bg-sky-50 px-1 text-[10px] text-sky-800">open</span>
                      )}
                      <div className="text-xs text-slate-500">{w.waits_on_title}</div>
                    </td>
                    <td className="py-2 text-xs">
                      {w.features.map((k) => {
                        const f = byKey.get(k);
                        return f ? (
                          <Link key={k} href={releasePath(project, name, `/features/${f.number}`)} className="block text-indigo-700 hover:underline">
                            #{f.number} {f.title}
                          </Link>
                        ) : null;
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-slate-500">None right now.</p>
          )}
        </section>

        <section className="rounded-lg border bg-white p-4 shadow-sm">
          <h2 className="font-semibold text-slate-800">SIGs that share features</h2>
          <p className="mb-3 text-xs text-slate-500">
            Features labelled with both SIGs, so the SIGs must coordinate. Counted per SIG, never per person.
          </p>
          <ul className="space-y-1.5 text-sm">
            {data.sig_pairs.slice(0, 10).map((p) => (
              <li key={p.a + p.b} className="grid grid-cols-[220px_1fr_28px] items-center gap-2">
                <span className="truncate text-slate-700">
                  {shortSig(p.a)} + {shortSig(p.b)}
                </span>
                <span className="h-2.5 rounded-r bg-indigo-300" style={{ width: `${(p.features / maxPair) * 100}%` }} aria-hidden />
                <span className="text-right font-medium text-slate-800">{p.features}</span>
              </li>
            ))}
          </ul>
          {data.sig_pairs.length > 10 && <p className="mt-2 text-xs text-slate-500">and {data.sig_pairs.length - 10} more pairs with fewer features</p>}
        </section>
      </div>

      <StandaloneTable rows={standalone} project={project} release={name} />
    </div>
  );
}

function StandaloneTable({ rows, project, release }: { rows: DepFeature[]; project: string; release: string }) {
  return (
    <section className="rounded-lg border bg-white p-4 shadow-sm">
      <h2 className="font-semibold text-slate-800">Stand-alone features ({rows.length})</h2>
      <p className="mb-3 text-xs text-slate-500">No shared PRs and no stated dependency on another feature.</p>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="py-1 pr-3">Feature</th>
              <th className="py-1 pr-3">SIGs</th>
              <th className="py-1 pr-3">PRs</th>
              <th className="py-1">Outcome</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((f) => {
              const merged = f.prs.filter((p) => p.state === "merged").length;
              const open = f.prs.filter((p) => p.state === "open").length;
              const meta = OUTCOME_META[f.outcome];
              return (
                <tr key={f.key}>
                  <td className="py-1.5 pr-3">
                    <Link href={releasePath(project, release, `/features/${f.number}`)} className="font-medium text-indigo-700 hover:underline">
                      #{f.number}
                    </Link>{" "}
                    {f.title}
                  </td>
                  <td className="py-1.5 pr-3 text-xs text-slate-600">{f.sigs.map(shortSig).join(", ")}</td>
                  <td className="py-1.5 pr-3 text-xs">
                    {merged}/{f.prs.length} merged{open ? ` · ${open} open` : ""}
                  </td>
                  <td className="py-1.5 text-xs">
                    <span className="mr-1 inline-block h-2 w-2 rounded-sm" style={{ background: STATUS[meta.status] }} />
                    {meta.label}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
