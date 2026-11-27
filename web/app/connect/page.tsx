// Connect your tools (UX vision p.7). Connector status and the release example come from
// GET /portfolio; a connector no live program reads is shown as Planned.
import Link from "next/link";
import { api } from "@/lib/api";
import { CONNECTORS, PROMISES, RELEASE_FIELDS, STEPS, usedBy } from "@/lib/connect";
import type { Portfolio } from "@/lib/portfolio";
import { releasePath } from "@/lib/routes";
import { programTitle } from "@/lib/names";

export const dynamic = "force-dynamic";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const date = (iso: string) => `${new Date(iso).getUTCDate()} ${MONTHS[new Date(iso).getUTCMonth()]} ${new Date(iso).getUTCFullYear()}`;

type Dates = Record<string, string | null>;
type Program = Portfolio["programs"][number] & { planning_tool?: string; code_tools?: string[]; dates?: Dates };

export default async function ConnectPage({ searchParams }: { searchParams: Promise<{ step?: string }> }) {
  const { step: raw } = await searchParams;
  const step = raw === "2" ? 2 : raw === "3" ? 3 : 1;
  let portfolio: Portfolio | null = null;
  let error: string | null = null;
  try {
    portfolio = await api.portfolio();
  } catch (e) {
    error = e instanceof Error ? e.message : "GET /portfolio failed";
  }
  const programs = (portfolio?.programs ?? []) as Program[];

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 py-4">
      <header>
        <h1 className="font-heading text-4xl font-bold tracking-tight">Plug in your org in three steps</h1>
        <p className="mt-2 text-slate-600">Read-only access. No source code is stored. Signing a company up is not open yet; the public demo shows what you get. <Link href="/connect/organization" className="underline">Your organizations</Link> lists the ones the API returns for you.</p>
      </header>

      <nav aria-label="Steps" className="grid gap-3 md:grid-cols-3">
        {STEPS.map((s) => {
          const on = s.n === step;
          return (
            <Link key={s.n} href={`/connect?step=${s.n}`} aria-current={on ? "step" : undefined}
              className={`rounded-2xl border px-6 py-5 ${on ? "border-action bg-action text-white" : "border-slate-200 bg-white text-slate-900 hover:border-slate-300"}`}>
              <span className={`block text-xs font-medium uppercase tracking-wider ${on ? "text-indigo-100" : "text-slate-500"}`}>Step {s.n}</span>
              <span className="mt-1 block font-heading text-lg font-semibold">{s.title}</span>
            </Link>
          );
        })}
      </nav>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 md:p-8">
        {error && <p className="mb-4 rounded-lg bg-critical-bg p-3 text-sm text-critical">Live programs could not be loaded. {error}</p>}
        {step === 1 && <StepConnect programs={programs} />}
        {step === 2 && <StepReleases programs={programs} />}
        {step === 3 && <StepProgram programs={programs} />}
      </section>

      <ul className="grid gap-3 md:grid-cols-3">
        {PROMISES.map((p) => (
          <li key={p.title} className="rounded-2xl border border-slate-200 bg-white p-6">
            <h2 className="font-heading text-lg font-semibold">{p.title}</h2>
            <p className="mt-1 text-slate-600">{p.body}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function StepConnect({ programs }: { programs: Program[] }) {
  return (
    <>
      <h2 className="font-heading text-2xl font-semibold">Connect where your plan and your work live</h2>
      <p className="mt-1 text-slate-600">Start with one planning tool and one code tool. Add conversations later.</p>
      <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {CONNECTORS.map((c) => {
          const users = usedBy(c, programs);
          return (
            <li key={c.id} className="flex flex-col rounded-xl border border-slate-200 p-5">
              <p className="font-heading text-lg font-semibold">{c.name}</p>
              <p className="mt-1 flex-1 text-sm text-slate-600">{c.reads}</p>
              <p className="mt-3">
                {users.length ? (
                  <span className="rounded-full bg-healthy-bg px-2.5 py-0.5 text-sm text-healthy">Available</span>
                ) : (
                  <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-sm text-slate-600">Planned</span>
                )}
              </p>
              {users.length > 0 && <p className="mt-2 text-xs text-slate-500">Live for {users.join(", ")}</p>}
            </li>
          );
        })}
      </ul>
    </>
  );
}

function StepReleases({ programs }: { programs: Program[] }) {
  const example = programs.find((p) => p.dates?.code_freeze_at && p.dates?.release_at) ?? null;
  return (
    <>
      <h2 className="font-heading text-2xl font-semibold">Describe your releases</h2>
      <p className="mt-1 text-slate-600">Four dates per release. The stage, the flags and the forecast all use them.</p>
      <div className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr>
              <th className="py-3 pr-4">Date</th>
              <th className="py-3 pr-4">What it means</th>
              {example && <th className="py-3 pr-4">Example: {programTitle(example.display_name, example.release, example.has_lab)}</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {RELEASE_FIELDS.map((f) => {
              const v = example?.dates?.[f.key];
              return (
                <tr key={f.key}>
                  <td className="py-3 pr-4 font-semibold">{f.name}</td>
                  <td className="py-3 pr-4 text-slate-600">{f.why}</td>
                  {example && <td className="py-3 pr-4">{v ? date(v) : "not set"}</td>}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-4 text-xs text-slate-500">Today each team describes its releases in a connector file (<code>connectors/teams/&lt;id&gt;.yaml</code>). Times are UTC.</p>
    </>
  );
}

function StepProgram({ programs }: { programs: Program[] }) {
  return (
    <>
      <h2 className="font-heading text-2xl font-semibold">See your first program</h2>
      <p className="mt-1 text-slate-600">Within one sync, the program shows its stage, scope, biggest bottleneck and next decision. These are filling in now:</p>
      {programs.length === 0 ? (
        <p className="mt-6 text-sm text-slate-600">No live programs yet.</p>
      ) : (
        <ul className="mt-6 grid gap-4 md:grid-cols-3">
          {programs.map((p) => (
            <li key={p.key}>
              <Link href={releasePath(p.project, p.release)} className="block rounded-xl border border-slate-200 p-5 hover:border-action">
                <p className="font-heading text-lg font-semibold">{programTitle(p.display_name, p.release, p.has_lab)}</p>
                <p className="mt-1 text-sm text-slate-600">{p.scope.features_in_release} features · {p.bottleneck.headline}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <Link href="/portfolio" className="mt-6 inline-flex min-h-11 items-center font-semibold text-action hover:underline">Open the portfolio →</Link>
    </>
  );
}
