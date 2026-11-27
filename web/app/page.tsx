// Front page (UX vision p.1–2). Programs come from GET /portfolio; story numbers from the
// release summary, feature #6395's timeline and the pod facts (GET /lab); the trust strip
// from lib/measured.ts. A missing source hides that piece and never shows a stand-in number.
import Link from "next/link";
import { api, type FeatureDetail, type Summary } from "@/lib/api";
import { fetchPodLab, type PodLab } from "@/lib/api-pdlc";
import { DEMO_CHAPTERS, DEMO_LENGTH, STAGES, fraction, freezeReplay, shortDate, trustTiles, trustProof, verdictSummary, teamCards, PIPELINE, STEP_TAG, TRUST_RULES, type Tag, type WaitingLite } from "@/lib/front";
import { frontStages, launchLearn } from "@/lib/stages";
import { MEASURED, VERDICT_LABEL, VERDICT_TONE } from "@/lib/measured";
import { stageLabel, type Portfolio, type PortfolioProgram } from "@/lib/portfolio";
import { releasePath } from "@/lib/routes";
import { programTitle } from "@/lib/names";

export const dynamic = "force-dynamic";

const REPLAY_FEATURE = 6395;

type Facts = {
  portfolio: Portfolio | null;
  error: string | null;
  summaries: Map<string, Summary>;
  pod: PodLab | null;
  replay: FeatureDetail | null;
};

async function load(): Promise<Facts> {
  let portfolio: Portfolio | null = null;
  let error: string | null = null;
  try {
    portfolio = await api.portfolio();
  } catch (e) {
    error = e instanceof Error ? e.message : "GET /portfolio failed";
  }
  const programs = portfolio?.programs ?? [];
  const kube = programs.find((p) => p.project.toLowerCase() === "kubernetes");
  const [sums, pod, replay] = await Promise.all([
    Promise.all(programs.filter((p) => !p.has_lab).map(async (p) => [p.key, await api.summary(p.release).catch(() => null)] as const)),
    programs.some((p) => p.has_lab) ? fetchPodLab().catch(() => null) : Promise.resolve(null),
    kube ? api.feature(kube.release, REPLAY_FEATURE).catch(() => null) : Promise.resolve(null),
  ]);
  const summaries = new Map<string, Summary>();
  for (const [key, s] of sums) if (s) summaries.set(key, s);
  return { portfolio, error, summaries, pod, replay };
}

export default async function FrontPage() {
  const facts = await load();
  const programs = facts.portfolio?.programs ?? [];
  const kube = programs.find((p) => p.project.toLowerCase() === "kubernetes");
  const tour = kube ?? programs[0];
  const tourHref = tour ? releasePath(tour.project, tour.release) : "/portfolio";
  const stages = frontStages(
    STAGES,
    launchLearn(
      facts.portfolio?.coming_next,
      {
        launch: tour ? releasePath(tour.project, tour.release, "/readiness") : "",
        learn: tour ? releasePath(tour.project, tour.release, "/retro") : "",
      },
      tour?.has_retro === true,
    ),
  );

  return (
    <div className="-mx-6 -my-6">
      <section className="bg-ink text-white">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-16 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:items-center">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.14em] text-indigo-300">AI-native program management · every fact verified</p>
            <h1 className="mt-4 font-heading text-4xl font-bold leading-[1.08] tracking-tight md:text-[3.4rem]">
              Run every program from plan to launch on facts, not just status meetings.
            </h1>
            <p className="mt-6 max-w-xl text-base leading-7 text-slate-300">
              Plug in the tools your teams already use. The platform tracks the real work, finds where delivery is stuck, forecasts the
              odds, lets leaders simulate a change before they commit, and drafts the update. AI explains. It never computes a number.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href={tourHref} className="inline-flex min-h-11 items-center rounded-lg bg-action px-5 text-sm font-semibold text-white hover:bg-action/90">
                Take the {DEMO_LENGTH.replace(/^(\d+):00$/, "$1")}-minute live tour →
              </Link>
              <Link href="/portfolio" className="inline-flex min-h-11 items-center rounded-lg border border-white/25 px-5 text-sm font-semibold text-white hover:bg-white/10">
                See every program
              </Link>
            </div>
            <p className="mt-6 text-xs text-slate-400">
              Live on real public data: Kubernetes (GitHub), Apache Kafka (Jira) and this platform&apos;s own repository.
            </p>
          </div>
          <LivePanel facts={facts} />
        </div>
      </section>

      <div className="mx-auto max-w-6xl space-y-16 px-6 py-16">
        <section>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-action">The whole program, one platform</p>
          <h2 className="mt-2 font-heading text-3xl font-semibold tracking-tight">From plan to launch, every stage has a module</h2>
          <p className="mt-2 text-sm text-slate-600">The same stages appear on every program in the product.</p>
          <ol className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {stages.map((s) => (
              <li key={s.stage} className="flex flex-col rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  {s.n} · {s.href ? <Link href={s.href} className="hover:text-action hover:underline">{s.stage}</Link> : s.stage}
                </p>
                <p className="mt-2 font-heading font-semibold leading-snug">{s.title}</p>
                <p className="mt-2 flex-1 text-xs leading-5 text-slate-600">{s.body}</p>
                <p className="mt-4 flex flex-wrap gap-1.5">{s.tags.map((t) => <Pill key={t.text} tag={t} />)}</p>
              </li>
            ))}
          </ol>
        </section>

        <section>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-action">Proof, not promises</p>
          <h2 className="mt-2 font-heading text-3xl font-semibold tracking-tight">Three real stories the platform tells today</h2>
          <Stories facts={facts} kube={kube} tourHref={tourHref} />
        </section>

        <HowItWorks />

        <TrustRules waiting={facts.portfolio?.waiting_on_you ?? []} />

        <Measured />

        <Teams programs={programs} />

        <Demo tourHref={tourHref} kube={kube} />
      </div>
    </div>
  );
}

function Pill({ tag }: { tag: Tag }) {
  const tone = {
    live: "bg-healthy-bg text-healthy",
    warn: "bg-warning-bg text-warning",
    next: "bg-indigo-50 text-action",
    planned: "bg-slate-100 text-slate-600",
  }[tag.tone];
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${tone}`}>{tag.text}</span>;
}

function LivePanel({ facts }: { facts: Facts }) {
  const programs = facts.portfolio?.programs ?? [];
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
      <div className="flex items-center justify-between text-[11px] uppercase tracking-wide text-slate-400">
        <span className="inline-flex items-center gap-2">
          <span aria-hidden className="h-2 w-2 rounded-full bg-emerald-400" />
          Live · {programs.length} program{programs.length === 1 ? "" : "s"}
        </span>
        {facts.portfolio && <span className="normal-case tracking-normal">as of {shortDate(facts.portfolio.as_of)}</span>}
      </div>
      {facts.error && <p className="mt-4 text-sm text-slate-300">Live programs could not be loaded. {facts.error}</p>}
      {!facts.error && programs.length === 0 && <p className="mt-4 text-sm text-slate-300">No live programs yet.</p>}
      <ul className="mt-4 space-y-2.5">
        {programs.map((p) => (
          <li key={p.key}>
            <Link href={releasePath(p.project, p.release)} className="block rounded-xl border border-white/10 bg-ink/60 px-4 py-3 hover:border-white/25">
              <span className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-semibold text-white">{programTitle(p.display_name, p.release, p.has_lab)}</span>
                <span className="shrink-0 text-xs font-medium text-indigo-300">{stageLabel(p.stage.current)} stage</span>
              </span>
              <span className="mt-1 block text-xs text-slate-400">{programLine(p, facts)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** One line of real facts per program. Unknown facts are left out, never guessed. */
function programLine(p: PortfolioProgram, facts: Facts): React.ReactNode {
  if (p.has_lab) {
    const pod = facts.pod?.pod;
    if (!pod) return `${p.scope.features_in_release} features planned`;
    const lanes = pod.members.length;
    const human = pod.flow.find((s) => s.stage === "human_review")?.value;
    return (
      <>
        Pod of {lanes}: Claude, Cursor, Dependabot, human
        {human && human.merged != null && (
          <span className="text-amber-300">
            {" "}· {human.merged} merged
            {human.approved_of ? `, ${human.approved ?? 0} approved by the human` : `, ${human.human_reviewed ?? "?"} with a human review`}
          </span>
        )}
      </>
    );
  }
  const s = facts.summaries.get(p.key);
  const freeze = p.dates?.code_freeze_at;
  if (s && s.phase === "after_freeze") {
    return `${s.features_in_release} features in · ${s.removed_at_freeze} removed at Code Freeze · ${s.critical_features} with a critical flag`;
  }
  const tool = p.planning_tool === "jira" ? " in Jira" : "";
  return `${p.scope.features_in_release} features planned${tool}${freeze ? ` · ${p.code_freeze_label || "Code Freeze"} ${shortDate(freeze)}` : ""}`;
}

function StoryCard({ eyebrow, big, of, tone, title, body, href, cta }: {
  eyebrow: string; big: string; of?: string; tone: string; title: string; body: string; href: string; cta: string;
}) {
  return (
    <li className="flex flex-col rounded-2xl border border-slate-200 bg-white p-6">
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{eyebrow}</p>
      <p className="mt-4 font-heading">
        <span className={`text-5xl font-bold ${tone}`}>{big}</span>
        {of && <span className="ml-2 text-xl font-semibold text-slate-500">{of}</span>}
      </p>
      <p className="mt-2 font-semibold text-slate-900">{title}</p>
      <p className="mt-2 flex-1 text-sm leading-6 text-slate-600">{body}</p>
      <Link href={href} className="mt-4 inline-flex min-h-11 items-center text-sm font-semibold text-action hover:underline">{cta} →</Link>
    </li>
  );
}

function Stories({ facts, kube, tourHref }: { facts: Facts; kube: PortfolioProgram | undefined; tourHref: string }) {
  const cards: React.ReactNode[] = [];
  const s = kube ? facts.summaries.get(kube.key) : undefined;
  if (kube && s && s.removed_at_freeze > 0) {
    const main = facts.replay?.pull_requests.find((pr) => pr.is_main);
    const readded = facts.replay ? facts.replay.in_release : false;
    const replay = freezeReplay(REPLAY_FEATURE, main?.created_at, main?.merged_at, kube.dates?.code_freeze_at, readded);
    cards.push(
      <StoryCard key="freeze" eyebrow={`${kube.display_name} ${kube.release} · GitHub`} big={String(s.removed_at_freeze)} tone="text-critical"
        title="features removed at Code Freeze"
        body={`Replay any past day.${replay ? ` ${replay}` : ""} The platform shows what was knowable, and when.`}
        href={tourHref} cta="Replay the release" />,
    );
  }
  const pod = facts.pod?.pod;
  const human = pod?.flow.find((st) => st.stage === "human_review")?.value;
  const merge = pod?.flow.find((st) => st.stage === "merge")?.value;
  if (human && human.merged != null && human.human_reviewed != null && human.merged > 0) {
    const median = merge?.median_minutes_to_merge;
    // With merges stored (ADR-0023 add. 3) the headline is the human's approval; written
    // reviews are the depth behind it.
    const approved = human.approved_of ? { n: human.approved ?? 0, of: human.approved_of } : null;
    cards.push(
      <StoryCard key="pod" eyebrow={`${facts.portfolio?.programs.find((p) => p.has_lab)?.display_name ?? "This platform"} · Claude + Cursor + Dependabot + human`}
        big={String(approved ? approved.n : human.human_reviewed)} of={`of ${approved ? approved.of : human.merged}`}
        tone="text-warning" title={approved ? "merged PRs approved by the human" : "merged PRs had a human review"}
        body={`${approved ? `${human.human_reviewed} of ${human.merged} also had a written human review. ` : ""}${median != null ? `Median time to merge: ${median} minutes. ` : ""}Agents write fast; verification is the gap. The platform measures it on its own development, honestly.`}
        href="/pdlc" cta="See the pod flow" />,
    );
  }
  const kafka = MEASURED.find((m) => m.id === "kafka-linking" && m.verdict !== "pending");
  const f = kafka ? fraction(kafka.value) : null;
  if (kafka && f) {
    const version = kafka.label.match(/\d+\.\d+\.\d+/)?.[0];
    cards.push(
      <StoryCard key="kafka" eyebrow={`Apache Kafka${version ? ` ${version}` : ""} · Jira + GitHub`} big={`${Math.round((f[0] / f[1]) * 100)}%`} tone="text-blue-600"
        title="of Jira features linked to real code"
        body={`${f[0]} of ${f[1]} features tied to merged PRs through Jira keys and sub-tasks. Same engine, a different planning tool: the plug-in model works.`}
        href="/portfolio" cta="Open the portfolio" />,
    );
  }
  if (cards.length === 0) return <p className="mt-6 text-sm text-slate-600">No story has live data right now.</p>;
  return <ul className="mt-6 grid gap-5 md:grid-cols-3">{cards}</ul>;
}

function HowItWorks() {
  return (
    <section>
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-action">How it works</p>
      <h2 className="mt-2 font-heading text-3xl font-semibold tracking-tight">From raw events to an update a VP can trust</h2>
      <ol className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
        {PIPELINE.map((step, i) => (
          <li key={step.n} className="relative flex flex-col rounded-2xl border border-slate-200 bg-white p-4">
            <p className="text-xs font-medium text-slate-400">{step.n}</p>
            <h3 className="mt-1 font-heading text-lg font-semibold">{step.title}</h3>
            <p className="mt-1 flex-1 text-sm leading-6 text-slate-600">{step.body}</p>
            <p className="mt-3">
              <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium leading-5 ${STEP_TAG[step.kind].tone}`}>{STEP_TAG[step.kind].text}</span>
            </p>
            {i < PIPELINE.length - 1 && <span aria-hidden className="absolute -right-2.5 top-1/2 hidden -translate-y-1/2 text-xs text-slate-300 xl:block">›</span>}
          </li>
        ))}
      </ol>
    </section>
  );
}

function Teams({ programs }: { programs: PortfolioProgram[] }) {
  const cards = teamCards(programs, (project, release) => releasePath(project, release));
  return (
    <section>
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-action">Any cross-functional team</p>
      <h2 className="mt-2 font-heading text-3xl font-semibold tracking-tight">One model for plans in GitHub or Jira</h2>
      <p className="mt-2 max-w-3xl text-slate-600">
        Collectors turn every source into the same events, so the facts, forecast and AI work the same way for every team.
      </p>
      <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((c) => {
          const body = (
            <>
              <span className="flex items-start justify-between gap-3">
                <span className="font-heading text-lg font-semibold text-slate-900">{c.name}</span>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${c.live ? "bg-healthy-bg text-healthy" : "bg-slate-100 text-slate-600"}`}>
                  {c.live ? "Live" : c.name === "Your team" ? "Plug in" : "Not live"}
                </span>
              </span>
              <span className="mt-2 block text-sm leading-6 text-slate-600">{c.body}</span>
            </>
          );
          return (
            <li key={c.name}>
              {c.href ? (
                <Link href={c.href} className="block h-full rounded-2xl border border-slate-200 bg-white p-5 hover:border-action">{body}</Link>
              ) : (
                <div className="h-full rounded-2xl border border-slate-200 bg-white p-5">{body}</div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function TrustRules({ waiting }: { waiting: WaitingLite[] }) {
  return (
    <section>
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-action">Trust by design</p>
      <h2 className="mt-2 font-heading text-3xl font-semibold tracking-tight">Three rules that make the AI safe to act on</h2>
      <ul className="mt-6 grid gap-5 md:grid-cols-3">
        {TRUST_RULES.map((r) => (
          <li key={r.id} className="flex flex-col rounded-2xl border border-slate-200 bg-white p-6">
            <h3 className="font-heading text-lg font-semibold">{r.title}</h3>
            <p className="mt-2 flex-1 text-sm leading-6 text-slate-600">{r.body}</p>
            <p className="mt-4 border-t border-slate-200 pt-4 text-sm leading-6 text-action">{trustProof(r.id, MEASURED, waiting)}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Measured() {
  const tiles = trustTiles(MEASURED);
  return (
    <section id="measured" className="scroll-mt-6 rounded-2xl border border-slate-200 bg-white p-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] lg:items-center">
        <div>
          <h2 className="font-heading text-2xl font-semibold">Measure, don&apos;t claim</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Rules and statistics compute every fact. AI reads messy text and writes the story. A fact checker removes any claim the
            data can&apos;t prove, and a person approves anything that leaves the platform. We publish the scorecard, failures included.
          </p>
          <p className="mt-3 text-sm font-medium text-slate-800">{verdictSummary(MEASURED)}</p>
        </div>
        <ul className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {tiles.map((t) => (
            <li key={t.label} className={`rounded-xl p-3.5 ${t.warn ? "bg-warning-bg" : "bg-slate-50"}`}>
              <p className={`font-heading text-2xl font-bold ${t.warn ? "text-warning" : "text-slate-900"}`}>{t.value}</p>
              <p className={`mt-1 text-xs leading-4 ${t.warn ? "text-warning" : "text-slate-600"}`}>{t.label}</p>
            </li>
          ))}
        </ul>
      </div>
      <details className="group mt-5 border-t border-slate-100 pt-4">
        <summary className="inline-flex min-h-11 cursor-pointer list-none items-center gap-2 text-sm font-semibold text-action">
          Every measured result, including what failed ({MEASURED.length})
          <span aria-hidden className="text-xs transition group-open:rotate-180">▾</span>
        </summary>
        <ul className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {MEASURED.map((item) => (
            <li key={item.id} className="flex flex-col rounded-xl border border-slate-200 p-4">
              <p><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${VERDICT_TONE[item.verdict]}`}>{VERDICT_LABEL[item.verdict]}</span></p>
              <p className="mt-2 font-heading text-xl font-semibold">{item.value}</p>
              <p className="text-sm text-slate-800">{item.label}</p>
              <p className="mt-1 flex-1 text-xs leading-5 text-slate-500">{item.detail}</p>
              <p className="mt-2 text-xs text-slate-400">{item.measured ? `Measured ${item.measured}` : "TBD (not yet measured)"}</p>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}

function Demo({ tourHref, kube }: { tourHref: string; kube: PortfolioProgram | undefined }) {
  const href: Record<string, string> = {
    front: "/",
    cockpit: tourHref,
    studio: kube ? releasePath(kube.project, kube.release, "/simulate") : "/portfolio",
    pdlc: "/pdlc",
    trust: "#measured",
  };
  return (
    <section>
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-action">Recorded demo</p>
      <h2 className="mt-2 font-heading text-3xl font-semibold tracking-tight">See it end to end in {DEMO_LENGTH.replace(/^(\d+):00$/, "$1")} minutes</h2>
      <div className="mt-6 grid overflow-hidden rounded-2xl bg-ink text-white md:grid-cols-[minmax(0,2.2fr)_minmax(0,1fr)]">
        <div className="flex min-h-[320px] flex-col items-center justify-center gap-4 bg-[#11173A] p-6">
          <span aria-hidden className="flex h-16 w-16 items-center justify-center rounded-full bg-action/60">
            <svg viewBox="0 0 16 16" className="ml-1 h-6 w-6 fill-white"><path d="M4 2.5v11l9-5.5z" /></svg>
          </span>
          <p className="text-sm text-slate-300">Recording not published yet · {DEMO_LENGTH}</p>
        </div>
        <div className="p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-300">Chapters</p>
          <ol className="mt-3 space-y-1">
            {DEMO_CHAPTERS.map((c, i) => (
              <li key={c.at}>
                <Link href={href[c.target]} className={`block rounded-lg px-3 py-2 ${i === 0 ? "border border-indigo-400/60 bg-action/30" : "hover:bg-white/5"}`}>
                  <span className="block text-[11px] text-slate-400">{c.at}</span>
                  <span className="block text-sm font-semibold">{c.title}</span>
                </Link>
              </li>
            ))}
          </ol>
          <Link href={tourHref} className="mt-4 inline-flex min-h-11 items-center px-3 text-sm font-semibold text-indigo-300 hover:underline">
            Prefer to explore? Try it live →
          </Link>
        </div>
      </div>
    </section>
  );
}
