// Front page: what Program Intelligence Platform is, how it works, and what has been measured.
// The live card uses the API's computed facts; the scorecard comes from
// lib/measured.ts (copied from the README, dated). No number here is written by AI.
import Link from "next/link";
import { Suspense } from "react";
import { api, type Outcome, type Release } from "@/lib/api";
import { OUTCOME_META, STATUS } from "@/lib/dashboard";
import { formatUtc } from "@/lib/format";
import { MEASURED, type Verdict } from "@/lib/measured";
import { currentRelease, groupByProject, releasePath } from "@/lib/routes";
import { SELF_PROJECT, teamState } from "@/lib/teams";

export const dynamic = "force-dynamic";

const DAY = 86_400_000;

export default async function FrontPage() {
  const releases = await api.releases().catch(() => [] as Release[]);
  const asOf = releases[0] ? new Date(releases[0].as_of) : new Date();
  const groups = groupByProject(releases);
  const cur = groups[0] ? currentRelease(groups[0].releases, asOf) : undefined;
  const base = cur ? releasePath(cur.project, cur.name) : "/releases";

  return (
    <div className="-mx-6 -my-6">
      <Hero release={cur} asOf={asOf} base={base} />
      <div className="space-y-16 px-6 py-14">
        <Pipeline />
        <Rules />
        <Modules base={base} release={cur} />
        <Scorecard />
        <Teams projects={groups.map((g) => g.displayName)} />
        <p className="border-t pt-6 text-center text-xs text-slate-500">
          Public data only (Kubernetes on GitHub; Apache Kafka on Jira and GitHub). Measures flow and bottlenecks per team, never individual
          performance. Decision support, not guarantees.
        </p>
      </div>
    </div>
  );
}

function Hero({ release, asOf, base }: { release?: Release; asOf: Date; base: string }) {
  return (
    <section className="relative overflow-hidden border-b bg-gradient-to-br from-indigo-50 via-white to-emerald-50/60">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-50 [background-image:radial-gradient(#c7d2fe_1px,transparent_1px)] [background-size:22px_22px]"
      />
      <div className="relative grid items-center gap-10 px-6 py-14 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div>
          <p className="mb-3 inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-white/80 px-3 py-1 text-xs font-medium text-indigo-700">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-500" /> AI-native program health
          </p>
          <h1 className="text-4xl font-semibold leading-tight tracking-tight text-slate-900 md:text-5xl">
            Know which features will slip,
            <br />
            <span className="text-indigo-700">and why, before the release does.</span>
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-slate-600">
            Program Intelligence Platform links the plan (KEPs, Jira issues) to the truth in the code (pull requests, reviews, CI). It computes the
            facts, forecasts the odds as ranges, maps dependencies between teams, and drafts the executive update.
          </p>
          <p className="mt-3 max-w-2xl text-slate-600">
            <strong className="font-semibold text-slate-800">AI explains; it never computes a number.</strong> Every AI sentence is
            checked against the data before anyone sees it, and a person approves anything that leaves.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href={base} className="rounded-md bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700">
              {release ? `Open ${release.display_name || release.project} ${release.name} live →` : "Open release health →"}
            </Link>
            <Link href="/releases" className="rounded-md border bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">
              All releases
            </Link>
            <a href="#measured" className="rounded-md px-4 py-2.5 text-sm font-medium text-indigo-700 hover:underline">
              See what we measured
            </a>
          </div>
        </div>
        {release ? (
          <Suspense fallback={<PulseShell release={release} asOf={asOf} base={base} />}>
            <Pulse release={release} asOf={asOf} base={base} />
          </Suspense>
        ) : (
          <div className="rounded-xl border bg-white/90 p-6 text-sm text-slate-500 shadow-sm">No release data collected yet.</div>
        )}
      </div>
    </section>
  );
}

function phaseOf(r: Release, asOf: Date): { label: string; tone: string } {
  const t = asOf.getTime();
  const at = (s: string | null) => (s ? new Date(s).getTime() : null);
  const days = (s: string | null) => Math.ceil(((at(s) ?? t) - t) / DAY);
  const cf = at(r.code_freeze_at);
  const rel = at(r.release_at);
  if (rel !== null && rel <= t) return { label: "Released", tone: "bg-slate-100 text-slate-700" };
  if (cf !== null && cf <= t)
    return { label: `After Code Freeze · release in ${days(r.release_at)} days`, tone: "bg-amber-50 text-amber-900" };
  if (cf !== null) return { label: `Code Freeze in ${days(r.code_freeze_at)} days`, tone: "bg-indigo-50 text-indigo-800" };
  return { label: "Dates not known", tone: "bg-slate-100 text-slate-700" };
}

function PulseShell({ release: r, asOf, base, children }: { release: Release; asOf: Date; base: string; children?: React.ReactNode }) {
  const phase = phaseOf(r, asOf);
  return (
    <Link href={base} className="block rounded-xl border bg-white/95 p-6 shadow-md ring-1 ring-black/[0.02] transition hover:shadow-lg">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
          </span>
          Live release pulse
        </p>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${phase.tone}`}>{phase.label}</span>
      </div>
      <p className="mt-2 text-2xl font-semibold text-slate-900">
        {r.display_name || r.project} {r.name}
      </p>
      {children ?? <p className="mt-6 text-sm text-slate-500">Computing release facts…</p>}
      <p className="mt-4 text-xs text-slate-500">Computed from public data as of {formatUtc(r.as_of)}. Open the dashboard →</p>
    </Link>
  );
}

async function Pulse({ release: r, asOf, base }: { release: Release; asOf: Date; base: string }) {
  const s = await api.summary(r.name).catch(() => null);
  if (!s)
    return (
      <PulseShell release={r} asOf={asOf} base={base}>
        <p className="mt-6 text-sm text-slate-500">Release facts are unavailable right now.</p>
      </PulseShell>
    );
  const order: Outcome[] = [
    "landed",
    "landed_prs_after_freeze",
    "landed_main_pr_open",
    "readded_after_freeze",
    "removed_after_freeze",
    "removed_at_freeze",
    "removed_before_freeze",
    "too_early",
  ];
  const segs = order.map((o) => ({ o, n: s.outcomes[o] ?? 0 })).filter((x) => x.n > 0);
  const total = segs.reduce((t, x) => t + x.n, 0) || 1;
  const stats: [string, number, string?][] = [
    ["In the release", s.features_in_release],
    ["Critical flag", s.critical_features, STATUS.critical],
    ["Open linked PRs", s.open_linked_prs],
  ];
  return (
    <PulseShell release={r} asOf={asOf} base={base}>
      <div className="mt-5 grid grid-cols-3 gap-3">
        {stats.map(([label, v, color]) => (
          <div key={label}>
            <p className="text-2xl font-semibold" style={{ color: color ?? "#0f172a" }}>
              {v}
            </p>
            <p className="text-xs text-slate-500">{label}</p>
          </div>
        ))}
      </div>
      <p className="mt-5 text-xs font-medium text-slate-600">What happened to all {s.features_ever} features that were ever in the release</p>
      <div className="mt-2 flex h-3 w-full gap-[2px] overflow-hidden rounded" role="img" aria-label="Features by outcome">
        {segs.map(({ o, n }) => (
          <div
            key={o}
            className="h-full first:rounded-l last:rounded-r"
            style={{ width: `${(n / total) * 100}%`, background: STATUS[OUTCOME_META[o].status] }}
            title={`${OUTCOME_META[o].label}: ${n}`}
          />
        ))}
      </div>
      <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-600">
        {segs.map(({ o, n }) => (
          <li key={o} className="flex items-center gap-1.5">
            <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: STATUS[OUTCOME_META[o].status] }} />
            <span className="truncate">{OUTCOME_META[o].label}</span>
            <span className="ml-auto font-medium text-slate-800">{n}</span>
          </li>
        ))}
      </ul>
    </PulseShell>
  );
}

type Kind = "rules" | "ai" | "human";
const KIND: Record<Kind, { label: string; cls: string }> = {
  rules: { label: "Deterministic", cls: "bg-slate-100 text-slate-700 border-slate-200" },
  ai: { label: "AI, then fact-checked", cls: "bg-violet-50 text-violet-800 border-violet-200" },
  human: { label: "Human", cls: "bg-emerald-50 text-emerald-800 border-emerald-200" },
};

const STEPS: { title: string; body: string; kind: Kind }[] = [
  { title: "Collect", body: "Issues, PRs, reviews, CI and history as timestamped events. Nothing is overwritten.", kind: "rules" },
  { title: "Link", body: "PR → feature → release from explicit keys and tracking lists. AI only suggests the rest.", kind: "rules" },
  { title: "Facts", body: "Freeze status, review rounds, critical path, rule flags. Counted, never guessed.", kind: "rules" },
  { title: "Forecast", body: "Monte Carlo odds per feature, shown as ranges next to the base rate.", kind: "rules" },
  { title: "Explain", body: "Agents turn facts into risk notes and a VP summary, one claim at a time.", kind: "ai" },
  { title: "Verify", body: "Each claim is checked against the database. Wrong or unsupported claims are removed and counted.", kind: "rules" },
  { title: "Approve", body: "A TPM edits and approves. The platform never sends anything on its own.", kind: "human" },
];

function Pipeline() {
  return (
    <section>
      <SectionHead eyebrow="How it works" title="From raw events to an update a VP can trust" />
      <ol className="mt-8 grid gap-3 md:grid-cols-4 xl:grid-cols-7">
        {STEPS.map((s, i) => (
          <li key={s.title} className="relative rounded-lg border bg-white p-4 shadow-sm">
            <p className="text-xs font-semibold text-slate-400">{String(i + 1).padStart(2, "0")}</p>
            <p className="mt-1 font-semibold text-slate-900">{s.title}</p>
            <p className="mt-1 text-sm text-slate-600">{s.body}</p>
            <span className={`mt-3 inline-block rounded-full border px-2 py-0.5 text-[11px] font-medium ${KIND[s.kind].cls}`}>
              {KIND[s.kind].label}
            </span>
            {i < STEPS.length - 1 && (
              <span aria-hidden className="absolute -right-2.5 top-1/2 z-10 hidden -translate-y-1/2 text-slate-300 xl:block">
                ▸
              </span>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

const RULES = [
  {
    title: "AI never computes facts",
    body: "Counts, dates, links, critical paths and odds come from code and statistics. AI is used for messy text and explanation only.",
    proof: "Every number on every page comes from a rule, a count or a statistical model.",
  },
  {
    title: "Every AI sentence is verified",
    body: "Agents return structured claims. The fact checker keeps a claim only if the database supports it, and publishes how many it removed.",
    proof: "43 / 43 agreement with labelled claims (measured 2026-11-22).",
  },
  {
    title: "Suggestions stay suggestions",
    body: "When AI proposes that a PR belongs to a feature, it is stored as suggested and never counts until a rule or a person confirms it.",
    proof: "104 v1.38 suggestions were waiting for review, none counted (measured 2026-11-22).",
  },
];

function Rules() {
  return (
    <section>
      <SectionHead eyebrow="Trust by design" title="Three rules that make the AI safe to act on" />
      <div className="mt-8 grid gap-4 md:grid-cols-3">
        {RULES.map((r) => (
          <div key={r.title} className="rounded-xl border bg-white p-6 shadow-sm">
            <p className="text-lg font-semibold text-slate-900">{r.title}</p>
            <p className="mt-2 text-sm text-slate-600">{r.body}</p>
            <p className="mt-4 border-t pt-3 text-sm font-medium text-indigo-700">{r.proof}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Modules({ base, release }: { base: string; release?: Release }) {
  const items = [
    { href: base, title: "Release health", body: "Tiles, what happened at Code Freeze, and every feature's flags, odds and linked PRs." },
    { href: `${base}/dependencies`, title: "Dependency map", body: "Which features share code or wait on each other, across teams, and which PRs are stuck." },
    { href: `${base}/simulate`, title: "What-if simulator", body: "Change reviewer staffing and see review waits as ranges. Labelled not validated until it is." },
    { href: `${base}/update`, title: "Verified executive brief", body: "An AI draft where every line was fact-checked, ready for a TPM to edit and approve." },
    { href: `${base}/links`, title: "Link review", body: "Confirm or reject AI-suggested links; only confirmed links change the facts." },
  ];
  return (
    <section>
      <SectionHead
        eyebrow="What you get"
        title={release ? `Live on ${release.display_name || release.project} ${release.name}` : "The modules"}
      />
      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {items.map((m) => (
          <Link key={m.title} href={m.href} className="group rounded-xl border bg-white p-5 shadow-sm transition hover:border-indigo-300 hover:shadow">
            <p className="font-semibold text-slate-900 group-hover:text-indigo-700">{m.title} →</p>
            <p className="mt-2 text-sm text-slate-600">{m.body}</p>
          </Link>
        ))}
      </div>
    </section>
  );
}

const VERDICT: Record<Verdict, { label: string; color: string; icon: string }> = {
  pass: { label: "Passes", color: STATUS.good, icon: "✓" },
  partial: { label: "Partly", color: "#b88a0e", icon: "◐" },
  fail: { label: "Fails", color: STATUS.critical, icon: "✕" },
  pending: { label: "Not measured", color: "#64748b", icon: "…" },
};

function Scorecard() {
  return (
    <section id="measured" className="scroll-mt-6">
      <SectionHead
        eyebrow="Measure, don't claim"
        title="What we measured, including what failed"
        sub="Every result is dated and reproducible from the repository. Where a model does not pass, the product says so on screen."
      />
      <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {MEASURED.map((m) => {
          const v = VERDICT[m.verdict];
          return (
            <div key={m.id} className="flex flex-col rounded-xl border bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm text-slate-600">{m.label}</p>
                <span className="shrink-0 text-xs font-medium" style={{ color: v.color }}>
                  {v.icon} {v.label}
                </span>
              </div>
              <p className="mt-2 text-3xl font-semibold text-slate-900">{m.value}</p>
              <p className="mt-2 flex-1 text-xs text-slate-500">{m.detail}</p>
              <p className="mt-3 text-[11px] text-slate-400">{m.measured ? `Measured ${m.measured}` : "TBD (not yet measured)"}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Teams({ projects }: { projects: string[] }) {
  const live = new Set(projects);
  const rows = [
    { name: "Kubernetes", how: "GitHub enhancement issues (KEPs) + kubernetes/kubernetes PRs" },
    { name: "Apache Kafka", how: "Jira fix versions (New Features, umbrellas, KIPs) + apache/kafka PRs; release dates only so far" },
    {
      name: SELF_PROJECT,
      how: "Tracks its own development: GitHub issues and the PRs that close them, delivered by GitHub webhooks in seconds",
    },
    { name: "Your team", how: "Copy a connector file: where the plan lives, where the code lives, the release calendar" },
  ];
  return (
    <section>
      <SectionHead
        eyebrow="Any cross-functional team"
        title="One model for plans in GitHub or Jira"
        sub="Collectors turn every source into the same events, so the facts, forecast and AI work the same way for every team."
      />
      <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {rows.map((r) => {
          const state = teamState(r.name, live);
          return (
            <div key={r.name} className="rounded-xl border bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between gap-2">
                <p className="font-semibold text-slate-900">{r.name}</p>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                    state === "Live" ? "bg-emerald-50 text-emerald-800" : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {state}
                </span>
              </div>
              <p className="mt-2 text-sm text-slate-600">{r.how}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function SectionHead({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <div className="max-w-3xl">
      <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600">{eyebrow}</p>
      <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">{title}</h2>
      {sub && <p className="mt-2 text-slate-600">{sub}</p>}
    </div>
  );
}
