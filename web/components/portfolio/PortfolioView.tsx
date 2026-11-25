// Portfolio (UX vision p.3). Every value is from GET /portfolio; this view only lays it out.
import Link from "next/link";
import { EmptyState } from "@/components/states/States";
import { formatUtc } from "@/lib/format";
import {
  STAGE_NAMES,
  approvalNotes,
  bottleneckTag,
  bottleneckText,
  decisionHref,
  missingRows,
  portfolioSummary,
  programSubline,
  severityClass,
  stageLabel,
  stageLine,
  waitingVerb,
  type Portfolio,
  type PortfolioProgram,
} from "@/lib/portfolio";
import { releasePath } from "@/lib/routes";
import { programTitle } from "@/lib/names";

export function PortfolioView({ data, stage }: { data: Portfolio; stage?: string | null }) {
  const shown = stage ? data.programs.filter((p) => p.stage.current === stage) : data.programs;
  return (
    <div className="mx-auto max-w-[1400px] space-y-8 py-4">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-4xl font-bold tracking-tight">Here are the live programs.</h1>
          <p className="mt-2 text-slate-600">{portfolioSummary(data.totals)}</p>
          <p className="mt-1 text-xs text-slate-500">Data as of {formatUtc(data.as_of)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <StageFilter current={stage ?? null} />
          <Link href="/connect" className="inline-flex min-h-11 items-center rounded-lg bg-action px-4 text-sm font-semibold text-white hover:bg-action/90">
            + Add a program
          </Link>
        </div>
      </header>
      <ProgramTable programs={shown} skipped={data.skipped} filtered={Boolean(stage)} />
      <div className="grid gap-5 lg:grid-cols-3">
        <Waiting data={data} />
        <Across items={data.across_programs} />
        <ComingNext items={data.coming_next} />
      </div>
      <CouldNotRead skipped={missingRows(data.skipped)} />
    </div>
  );
}

function StageFilter({ current }: { current: string | null }) {
  return (
    <details className="relative">
      <summary className="inline-flex min-h-11 cursor-pointer list-none items-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800">
        {current ? `Stage: ${stageLabel(current)}` : "All stages"} <span aria-hidden className="ml-2 text-xs">▾</span>
      </summary>
      <ul className="absolute right-0 z-10 mt-1 w-40 rounded-lg border bg-white py-1 shadow-lg">
        <li><Link href="/portfolio" className="flex min-h-11 items-center px-3 text-sm hover:bg-slate-50">All stages</Link></li>
        {STAGE_NAMES.map((s) => (
          <li key={s}>
            <Link href={`/portfolio?stage=${s}`} aria-current={current === s ? "true" : undefined} className="flex min-h-11 items-center px-3 text-sm hover:bg-slate-50">
              {stageLabel(s)}
            </Link>
          </li>
        ))}
      </ul>
    </details>
  );
}

const TH = "px-6 py-4 text-left text-xs font-medium uppercase tracking-wider text-slate-500";

function ProgramTable({ programs, skipped, filtered }: { programs: PortfolioProgram[]; skipped: Portfolio["skipped"]; filtered: boolean }) {
  if (programs.length === 0) {
    return filtered
      ? <EmptyState title="No program is in this stage" body="Choose All stages to see every program." />
      : <EmptyState title="No programs yet" body="No team has a release the portfolio can show." />;
  }
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
      <table className="w-full min-w-[960px] text-sm">
        <thead className="border-b border-slate-200">
          <tr>
            <th className={TH}>Program</th>
            <th className={TH}>Where it is: stage: Plan → Build → Freeze → Launch → Learn</th>
            <th className={TH}>Scope</th>
            <th className={TH}>Biggest bottleneck</th>
            <th className={TH}>Next decision</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {programs.map((p) => {
            const href = p.next_decision ? decisionHref(p.project, p.release, p.next_decision.kind) : null;
            const text = bottleneckText(p.bottleneck);
            return (
              <tr key={p.key} className="align-middle">
                <td className="px-6 py-5">
                  <Link href={releasePath(p.project, p.release)} className="font-heading text-base font-semibold text-slate-900 hover:text-action hover:underline">
                    {programTitle(p.display_name, p.release, p.has_lab)}
                  </Link>
                  <p className="mt-0.5 text-slate-500">{p.has_lab ? "This repo · Claude, Cursor, Dependabot, human" : programSubline(p)}</p>
                  {approvalNotes(p.project, skipped).map((note) => (
                    <p key={note} className="mt-1 text-xs text-warning">{note}</p>
                  ))}
                </td>
                <td className="w-[28%] px-6 py-5">
                  <StageBar stages={p.stage.stages} />
                  <p className="mt-2 text-slate-600">{stageLine(p)}</p>
                </td>
                <td className="px-6 py-5">
                  <p className="font-heading text-2xl font-bold text-slate-900">{p.scope.features_in_release}</p>
                  <p className="whitespace-nowrap text-slate-500">{p.has_lab ? "features planned" : `features in · ${p.scope.features_ever} ever`}</p>
                </td>
                <td className="px-6 py-5">
                  <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${severityClass(p.bottleneck.severity)}`}>
                    {bottleneckTag(p.bottleneck)}
                  </span>
                  {text && <p className="mt-1.5 text-slate-600">{text}</p>}
                </td>
                <td className="px-6 py-5">
                  {p.next_decision ? (
                    href ? (
                      <Link href={href} className="inline-flex min-h-11 items-center font-semibold text-action hover:underline">{p.next_decision.label} →</Link>
                    ) : (
                      <span className="text-slate-600">{p.next_decision.label}</span>
                    )
                  ) : (
                    <span className="text-slate-500">Nothing waiting</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function StageBar({ stages }: { stages: { name: string; status: string }[] }) {
  const text = stages.map((s) => `${stageLabel(s.name)} ${s.status}`).join(", ");
  return (
    <div className="flex gap-1.5" role="img" aria-label={text}>
      {stages.map((s) => (
        <span
          key={s.name}
          className={`h-2 flex-1 rounded-full ${s.status === "done" ? "bg-action" : s.status === "current" ? "bg-indigo-300" : "bg-slate-200"}`}
        />
      ))}
    </div>
  );
}

const CARD = "rounded-2xl border border-slate-200 bg-white p-6";

function Waiting({ data }: { data: Portfolio }) {
  return (
    <section className={CARD}>
      <h2 className="font-heading text-xl font-semibold">Waiting on you</h2>
      <p className="mt-1 text-sm text-slate-500">Nothing leaves the platform until you approve it.</p>
      {data.waiting_on_you.length === 0 ? (
        <p className="mt-4 text-sm text-slate-600">Nothing waiting.</p>
      ) : (
        <ul className="mt-4 space-y-2.5">
          {data.waiting_on_you.map((item) => {
            const program = data.programs.find((p) => p.key === item.program_key);
            const href = program ? decisionHref(program.project, program.release, item.kind) : null;
            return (
              <li key={`${item.program_key}-${item.kind}`} className="flex min-h-11 items-center justify-between gap-3 rounded-lg bg-slate-50 px-4 py-2.5 text-sm">
                <span className="text-slate-800">{item.label}</span>
                {href && <Link href={href} className="shrink-0 font-semibold text-action hover:underline">{waitingVerb(item.kind)}</Link>}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** One heading per pattern; programs that share it are listed under it. */
function groupByTitle(items: Portfolio["across_programs"]): { title: string; texts: string[] }[] {
  const out: { title: string; texts: string[] }[] = [];
  for (const item of items) {
    const group = out.find((g) => g.title === item.title);
    if (group) group.texts.push(item.text);
    else out.push({ title: item.title, texts: [item.text] });
  }
  return out;
}

function Across({ items }: { items: Portfolio["across_programs"] }) {
  return (
    <section className={CARD}>
      <h2 className="font-heading text-xl font-semibold">Across programs</h2>
      <p className="mt-1 text-sm text-slate-500">Patterns the platform sees in more than one program.</p>
      {items.length === 0 ? (
        <p className="mt-4 text-sm text-slate-600">No pattern yet.</p>
      ) : (
        <ul className="mt-4 space-y-4">
          {groupByTitle(items).map((group) => (
            <li key={group.title}>
              <p className="text-sm font-semibold text-slate-900">{group.title}</p>
              {group.texts.map((text) => (
                <p key={text} className="mt-0.5 text-sm leading-6 text-slate-600">{text}</p>
              ))}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const SHORT: Record<string, string> = { raid: "RAID", readiness: "readiness", retro: "retros" };

function ComingNext({ items }: { items: Portfolio["coming_next"] }) {
  const names = items.map((i) => SHORT[i.module] ?? i.name);
  const title = names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}` : (names[0] ?? "");
  const planned = items.length > 0 && items.every((i) => i.status === "planned");
  return (
    <section className="rounded-2xl bg-ink p-6 text-white">
      <p className="text-xs font-medium uppercase tracking-wider text-indigo-300">Coming next · Preview</p>
      <h2 className="mt-2 font-heading text-xl font-semibold">{title || "Nothing planned"}</h2>
      <p className="mt-3 text-sm leading-6 text-slate-300">
        Risks and decisions pulled from meeting notes, a go/no-go from real signals before launch, and a retro that shows when each slip was first visible.
      </p>
      <p className="mt-4">
        <span className="inline-block rounded-full border border-white/25 px-3 py-1 text-xs text-slate-200">
          {planned ? "Planned modules · no data yet" : items.map((i) => `${i.name} · ${i.status}`).join(" · ")}
        </span>
      </p>
    </section>
  );
}

function CouldNotRead({ skipped }: { skipped: Portfolio["skipped"] }) {
  if (skipped.length === 0) return null;
  return (
    <section>
      <h2 className="font-heading text-lg font-semibold">Could not read</h2>
      <ul className="mt-2 space-y-1 text-sm text-slate-600">
        {skipped.map((s) => (
          <li key={`${s.team}-${s.reason}`}>{s.team}: {s.reason}</li>
        ))}
      </ul>
    </section>
  );
}
