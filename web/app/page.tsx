// Front page. Live programs come from GET /portfolio. Story counts come from the
// release summary, the lab report, or lib/measured.ts. A missing source omits that story.
import Link from "next/link";
import { api } from "@/lib/api";
import { DEMO_CHAPTERS, DEMO_LENGTH, STAGE_MODULES, freezeStory, measuredStory, reviewStory, type Story } from "@/lib/front";
import { formatUtc } from "@/lib/format";
import { MEASURED, type Verdict } from "@/lib/measured";
import { stageLabel, type Portfolio, type PortfolioProgram } from "@/lib/portfolio";
import { releasePath } from "@/lib/routes";

export const dynamic = "force-dynamic";

const VERDICT: Record<Verdict, string> = {
  pass: "Passes",
  partial: "Partly",
  fail: "Fails",
  pending: "Not measured",
};

export default async function FrontPage() {
  let portfolio: Portfolio | null = null;
  let error: string | null = null;
  try {
    portfolio = await api.portfolio();
  } catch (e) {
    error = e instanceof Error ? e.message : "GET /portfolio failed";
  }
  const programs = portfolio?.programs ?? [];
  const first = programs[0];
  const demoHref = first ? releasePath(first.project, first.release) : "/releases";
  const stories = portfolio ? await storiesFor(portfolio) : [];

  return (
    <div className="-mx-6 -my-6">
      <section className="bg-ink px-6 py-14 text-white">
        <p className="text-sm text-slate-300">AI-native program management · every fact verified</p>
        <h1 className="mt-3 max-w-4xl font-heading text-4xl font-semibold leading-tight tracking-tight md:text-5xl">
          Run every program from plan to launch on facts, now that agents write the code.
        </h1>
        <div className="mt-8">
          <Link href={demoHref} className="inline-flex min-h-11 items-center rounded-md bg-action px-4 text-sm font-medium text-white">
            Open the live demo
          </Link>
        </div>
        {error && <p className="mt-8 max-w-2xl text-sm text-slate-200">Live programs could not be loaded. {error}</p>}
        {!error && programs.length === 0 && <p className="mt-8 text-sm text-slate-300">No live programs yet.</p>}
        {programs.length > 0 && (
          <ul className="mt-10 grid gap-3 md:grid-cols-3">
            {programs.map((program) => (
              <li key={program.key}>
                <ProgramCard program={program} />
              </li>
            ))}
          </ul>
        )}
        {portfolio && <p className="mt-4 text-xs text-slate-400">Data as of {formatUtc(portfolio.as_of)}</p>}
      </section>

      <div className="space-y-14 px-6 py-14">
        <section>
          <h2 className="font-heading text-2xl font-semibold">Plan · Build · Freeze · Launch · Learn</h2>
          <ol className="mt-6 grid gap-3 sm:grid-cols-5">
            {STAGE_MODULES.map((item) => (
              <li key={item.stage} className="rounded-lg border bg-white p-4">
                <p className="font-semibold">{item.stage}</p>
                <p className="mt-1 text-sm text-slate-600">{item.module}</p>
                <p className="mt-2 text-xs font-medium text-slate-500">{item.status}</p>
              </li>
            ))}
          </ol>
        </section>

        <section>
          <h2 className="font-heading text-2xl font-semibold">Three things the data already shows</h2>
          {stories.length === 0 ? (
            <p className="mt-4 text-sm text-slate-600">No measured story is available right now.</p>
          ) : (
            <ul className="mt-6 grid gap-4 md:grid-cols-3">
              {stories.map((story) => (
                <li key={story.title} className="rounded-lg border bg-white p-5">
                  <p className="text-xl font-semibold">{story.title}</p>
                  <p className="mt-2 text-sm text-slate-600">{story.detail}</p>
                  <p className="mt-3 text-xs text-slate-500">Data as of {story.asOf.includes("T") ? formatUtc(story.asOf) : story.asOf}</p>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section id="measured">
          <h2 className="font-heading text-2xl font-semibold">Built for trust</h2>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">Dated results from the repository, including the ones that failed.</p>
          <ul className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {MEASURED.map((item) => (
              <li key={item.id} className="rounded-lg border bg-white p-4">
                <p className="text-xs text-slate-500">{VERDICT[item.verdict]}</p>
                <p className="mt-1 text-2xl font-semibold">{item.value}</p>
                <p className="mt-1 text-sm text-slate-700">{item.label}</p>
                <p className="mt-2 text-xs text-slate-500">{item.detail}</p>
                <p className="mt-2 text-xs text-slate-400">{item.measured ? `Measured ${item.measured}` : "TBD (not yet measured)"}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-lg bg-ink p-6 text-white">
          <h2 className="font-heading text-2xl font-semibold">Recorded demo · {DEMO_LENGTH}</h2>
          <p className="mt-2 text-sm text-slate-300">No recording is published yet. The five chapters are:</p>
          <ol className="mt-4 list-decimal space-y-1 pl-5 text-sm">
            {DEMO_CHAPTERS.map((chapter) => (
              <li key={chapter}>{chapter}</li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  );
}

function ProgramCard({ program }: { program: PortfolioProgram }) {
  return (
    <Link href={releasePath(program.project, program.release)} className="block rounded-lg bg-white/10 p-4 hover:bg-white/15">
      <p className="text-lg font-semibold">{program.display_name}</p>
      <p className="text-sm text-slate-300">{program.release}</p>
      <p className="mt-2 text-sm">{stageLabel(program.stage.current)}</p>
      <p className="mt-1 text-xs text-slate-400">{program.scope.features_in_release} in the release</p>
    </Link>
  );
}

async function storiesFor(portfolio: Portfolio): Promise<Story[]> {
  const kubernetes = portfolio.programs.find((program) => program.project.toLowerCase() === "kubernetes");
  const repo = portfolio.programs.find((program) => program.project === "tpm-intelligence");
  const [summary, lab] = await Promise.all([
    kubernetes ? api.summary(kubernetes.release).catch(() => null) : null,
    repo ? api.lab(repo.project, repo.release).catch(() => null) : null,
  ]);
  const stories = [
    kubernetes && summary ? freezeStory(kubernetes.display_name, kubernetes.release, summary.removed_at_freeze, summary.as_of) : null,
    repo && lab?.lanes_configured ? reviewStory(repo.display_name, lab.approved_merged, lab.n_merged, lab.as_of) : null,
    measuredStory(MEASURED, "kafka-linking"),
  ];
  return stories.filter((story): story is Story => story !== null);
}
