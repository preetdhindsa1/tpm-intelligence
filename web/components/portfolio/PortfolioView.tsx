import Link from "next/link";
import { EmptyState } from "@/components/states/States";
import { formatUtc } from "@/lib/format";
import {
  approvalNotes,
  decisionHref,
  missingRows,
  portfolioSummary,
  severityClass,
  stageLabel,
  statusLabel,
  type Portfolio,
  type PortfolioProgram,
} from "@/lib/portfolio";
import { releasePath } from "@/lib/routes";

export function PortfolioView({ data }: { data: Portfolio }) {
  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold">Here are the live programs.</h1>
        <p className="mt-1 text-sm text-slate-600">
          {portfolioSummary(data.totals)} · data as of {formatUtc(data.as_of)}
        </p>
      </header>
      <ProgramTable programs={data.programs} skipped={data.skipped} />
      <Waiting data={data} />
      <Across items={data.across_programs} />
      <ComingNext items={data.coming_next} />
      <CouldNotRead skipped={missingRows(data.skipped)} />
    </div>
  );
}

function ProgramTable({ programs, skipped }: { programs: PortfolioProgram[]; skipped: Portfolio["skipped"] }) {
  if (programs.length === 0) return <EmptyState title="No programs yet" body="No team has a release the portfolio can show." />;
  return (
    <div className="overflow-x-auto rounded-lg border bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs text-slate-500">
          <tr>
            <th className="px-3 py-2 font-medium">Program</th>
            <th className="px-3 py-2 font-medium">Stage</th>
            <th className="px-3 py-2 font-medium">Scope</th>
            <th className="px-3 py-2 font-medium">Biggest bottleneck</th>
            <th className="px-3 py-2 font-medium">Next decision</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {programs.map((p) => {
            const href = p.next_decision ? decisionHref(p.project, p.release, p.next_decision.kind) : null;
            return (
              <tr key={p.key} className="align-top">
                <td className="px-3 py-3">
                  <Link href={releasePath(p.project, p.release)} className="font-medium text-action hover:underline">
                    {p.display_name}
                  </Link>
                  <div className="text-xs text-slate-500">{p.release}</div>
                  {approvalNotes(p.project, skipped).map((note) => (
                    <p key={note} className="mt-1 text-xs text-warning">{note}</p>
                  ))}
                </td>
                <td className="px-3 py-3">
                  <StageBar stages={p.stage.stages} />
                  <div className="mt-1 text-xs text-slate-600">
                    {stageLabel(p.stage.current)}
                    {p.stage.days_to_next_milestone !== null && p.stage.next_milestone
                      ? ` · ${p.stage.days_to_next_milestone} days to ${p.stage.next_milestone.name.replaceAll("_", " ")}`
                      : ""}
                  </div>
                </td>
                <td className="px-3 py-3 text-slate-700">
                  {p.scope.features_in_release} in the release
                  <div className="text-xs text-slate-500">{p.scope.features_ever} ever</div>
                </td>
                <td className="px-3 py-3">
                  <span className={`rounded px-2 py-0.5 text-xs font-medium ${severityClass(p.bottleneck.severity)}`}>{p.bottleneck.headline}</span>
                  {p.bottleneck.detail && <p className="mt-1 text-xs text-slate-600">{p.bottleneck.detail}</p>}
                </td>
                <td className="px-3 py-3">
                  {p.next_decision ? (
                    href ? <Link href={href} className="text-action hover:underline">{p.next_decision.label}</Link> : p.next_decision.label
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
    <div className="flex w-36 gap-1" role="img" aria-label={text}>
      {stages.map((s) => (
        <span key={s.name} className={`h-2 flex-1 rounded-sm ${s.status === "current" ? "bg-action" : s.status === "done" ? "bg-action/40" : "bg-slate-200"}`} />
      ))}
    </div>
  );
}

function CouldNotRead({ skipped }: { skipped: Portfolio["skipped"] }) {
  if (skipped.length === 0) return null;
  return (
    <section>
      <h2 className="text-lg font-semibold">Could not read</h2>
      <ul className="mt-2 space-y-1 text-sm text-slate-600">
        {skipped.map((s) => (
          <li key={`${s.team}-${s.reason}`}>{s.team}: {s.reason}</li>
        ))}
      </ul>
    </section>
  );
}

function Waiting({ data }: { data: Portfolio }) {
  return (
    <section>
      <h2 className="text-lg font-semibold">Waiting on you</h2>
      {data.waiting_on_you.length === 0 ? (
        <p className="mt-2 text-sm text-slate-600">Nothing waiting.</p>
      ) : (
        <ul className="mt-2 space-y-1 text-sm">
          {data.waiting_on_you.map((item) => {
            const program = data.programs.find((p) => p.key === item.program_key);
            const href = program ? decisionHref(program.project, program.release, item.kind) : null;
            return (
              <li key={`${item.program_key}-${item.kind}`}>
                {href ? <Link href={href} className="text-action hover:underline">{item.label}</Link> : item.label}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Across({ items }: { items: Portfolio["across_programs"] }) {
  if (items.length === 0) return null;
  return (
    <section>
      <h2 className="text-lg font-semibold">Across programs</h2>
      <ul className="mt-2 space-y-2">
        {items.map((item) => (
          <li key={`${item.program_key}-${item.kind}`} className="rounded-lg border bg-white p-3">
            <p className="text-sm font-medium">{item.title}</p>
            <p className="text-sm text-slate-600">{item.text}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ComingNext({ items }: { items: Portfolio["coming_next"] }) {
  return (
    <section>
      <h2 className="text-lg font-semibold">Coming next</h2>
      <ul className="mt-2 flex flex-wrap gap-2">
        {items.map((item) => (
          <li key={item.module} className="rounded-lg border bg-white px-3 py-2 text-sm">
            {item.name} <span className="ml-2 rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{statusLabel(item.status)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
