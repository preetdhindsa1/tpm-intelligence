"use client";

// Decision Studio (UX vision p.5, ADR-0012). Every number comes from the API's simulator;
// this page only shows it. Baseline is always next to the scenario, and results are ranges.
import Link from "next/link";
import { useMe } from "@/components/Me";
import { EmptyState, ErrorState, LoadingState } from "@/components/states/States";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  updatesRequest,
  type PoolChange,
  type PoolOutcome,
  type SavedScenario,
  type ScenarioSettings,
  type Simulation,
  type SimulatorInfo,
} from "@/lib/api";
import { simValidationText } from "@/lib/cockpit";
import { daysLabel, formatUtc, rangeLabel, simDelta, type SimDelta } from "@/lib/format";
import { STUDIO_LEVERS, leverSettings, mergedLine, poolName, poolsByLoad, scenarioNotes, type LeverId } from "@/lib/studio";

const LOW_EFFORT_DAYS = 0.03; // the fit's lower bound is 0.02 days (simulator/replay.py)
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const short = (iso: string) => `${new Date(iso).getUTCDate()} ${MONTHS[new Date(iso).getUTCMonth()]}`;
const shortYear = (iso: string) => `${short(iso)} ${new Date(iso).getUTCFullYear()}`;
const rel = (r: string) => r.split(":").pop() ?? r;

function changed(c: PoolChange | undefined): boolean {
  return !!c && (c.reviewers !== 0 || c.new_reviewers !== 0 || c.interruption !== 0);
}

function Delta({ d }: { d: SimDelta | null }) {
  if (!d) return <span className="text-slate-400">—</span>;
  const tone =
    d.tone === "same"
      ? "text-slate-500"
      : d.tone === "better"
        ? "bg-emerald-50 text-emerald-800"
        : "bg-rose-50 text-rose-800";
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${tone}`} title={d.overlaps ? "Ranges overlap: may be noise" : undefined}>
      {d.text}
      {d.overlaps && d.tone !== "same" ? " ~" : ""}
    </span>
  );
}


function ResultRow({ base, scen, bold }: { base: PoolOutcome; scen: PoolOutcome; bold?: boolean }) {
  const reviewers =
    base.reviewers === null ? "" : base.reviewers === scen.reviewers ? `${base.reviewers}` : `${base.reviewers} → ${scen.reviewers}`;
  return (
    <tr className={`border-t ${bold ? "font-semibold" : ""}`}>
      <td className="py-1.5">{base.pool === "all" ? "All pools" : base.pool}</td>
      <td>{reviewers}</td>
      <td>{rangeLabel(base.review_wait_days, "days")}</td>
      <td>{rangeLabel(scen.review_wait_days, "days")}</td>
      <td>
        <Delta d={simDelta(base.review_wait_days, scen.review_wait_days, "days", true)} />
      </td>
      <td>{rangeLabel(base.merged, "count")}</td>
      <td>{rangeLabel(scen.merged, "count")}</td>
      <td>
        <Delta d={simDelta(base.merged, scen.merged, "count", false)} />
      </td>
      <td>{rangeLabel(scen.not_merged, "count")}</td>
    </tr>
  );
}

function Results({ sim, onlyChanged }: { sim: Simulation; onlyChanged: boolean }) {
  const touched = new Set(Object.entries(sim.scenario.scenario.pools).filter(([, c]) => changed(c)).map(([p]) => p));
  const order = (a: PoolOutcome, b: PoolOutcome) => Number(a.pool === "other") - Number(b.pool === "other") || a.pool.localeCompare(b.pool);
  const rows = [...sim.baseline.pools].sort(order).filter((p) => !onlyChanged || touched.has(p.pool) || sim.scenario.scenario.arrival_multiplier !== 1);
  return (
    <div className="overflow-x-auto rounded-lg border bg-white">
      <div className="overflow-x-auto"><table className="w-full text-left text-sm [&_td]:px-3 [&_th]:px-3">
        <thead className="bg-slate-50 text-xs text-slate-500">
          <tr>
            <th className="py-2">Pool</th>
            <th>Reviewers</th>
            <th>Review wait · baseline</th>
            <th>Review wait · scenario</th>
            <th>Δ</th>
            <th>Merged by {sim.horizon_label} · baseline</th>
            <th>Merged · scenario</th>
            <th>Δ</th>
            <th>Not merged · scenario</th>
          </tr>
        </thead>
        <tbody>
          <ResultRow base={sim.baseline.total} scen={sim.scenario.total} bold />
          {rows.map((b) => (
            <ResultRow key={b.pool} base={b} scen={sim.scenario.pools.find((s) => s.pool === b.pool)!} />
          ))}
        </tbody>
      </table></div>
      <p className="border-t px-3 py-2 text-xs text-slate-500">
        {sim.note} Medians with 10th–90th percentile over {sim.replications} runs (seed {sim.seed}); &quot;~&quot; means the ranges
        overlap. Computed in {sim.seconds.toFixed(2)} s.
      </p>
    </div>
  );
}

function Compare({ a, b }: { a: SavedScenario; b: SavedScenario }) {
  const pools = a.result.scenario.pools.map((p) => p.pool);
  const row = (label: string, x: PoolOutcome | undefined, y: PoolOutcome | undefined) => (
    <tr key={label} className="border-t">
      <td className="py-1.5">{label}</td>
      <td>{rangeLabel(x?.review_wait_days ?? null, "days")}</td>
      <td>{rangeLabel(y?.review_wait_days ?? null, "days")}</td>
      <td>
        <Delta d={simDelta(x?.review_wait_days ?? null, y?.review_wait_days ?? null, "days", true)} />
      </td>
      <td>{rangeLabel(x?.merged ?? null, "count")}</td>
      <td>{rangeLabel(y?.merged ?? null, "count")}</td>
    </tr>
  );
  return (
    <div className="overflow-x-auto rounded-lg border bg-white">
      <p className="px-3 pt-2 text-sm font-medium">
        {a.name} vs {b.name}
        {a.calibration_id !== b.calibration_id && (
          <span className="ml-2 text-xs font-normal text-amber-700">(different calibrations: not directly comparable)</span>
        )}
      </p>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm">
        <thead className="text-xs text-slate-500">
          <tr>
            <th className="py-2">Pool</th>
            <th>Wait · {a.name}</th>
            <th>Wait · {b.name}</th>
            <th>Δ</th>
            <th>Merged · {a.name}</th>
            <th>Merged · {b.name}</th>
          </tr>
        </thead>
        <tbody>
          {row("All pools", a.result.scenario.total, b.result.scenario.total)}
          {pools.map((p) =>
            row(
              p,
              a.result.scenario.pools.find((x) => x.pool === p),
              b.result.scenario.pools.find((x) => x.pool === p),
            ),
          )}
        </tbody>
      </table></div>
    </div>
  );
}


function Banner({ info, releaseKey }: { info: SimulatorInfo; releaseKey: string }) {
  const text = simValidationText(info.validation, releaseKey);
  return (
    <div className={`rounded-xl border px-5 py-3.5 text-sm ${info.validated ? "border-emerald-200 bg-healthy-bg text-healthy" : "border-amber-200 bg-warning-bg text-warning"}`}>
      <p>
        <strong>Powered by the Shadow-Org Simulator · {info.validated ? "validated" : "not validated"}.</strong>
        {text && <span className="ml-3">{text}</span>}
      </p>
      {!info.validated && info.effort_days <= LOW_EFFORT_DAYS && (
        <p className="mt-1">
          The fitted reviewer time per round is at its lower limit ({daysLabel(info.effort_days)}), so in this model reviewer capacity has
          little effect: adding or removing reviewers moves waits less than it likely would in reality.
        </p>
      )}
    </div>
  );
}

function Assumptions({ info }: { info: SimulatorInfo }) {
  const TH = "py-3 pr-4 text-left text-xs font-medium uppercase tracking-wider text-slate-500";
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <h2 className="font-heading text-xl font-semibold">Assumptions used · all measured</h2>
      <p className="mt-1 text-sm text-slate-500">
        Starts from the {info.pools.reduce((n, p) => n + p.open_prs_now, 0)} open PRs of this release ({formatUtc(info.as_of)}). Each PR follows a
        real PR&apos;s review path from the source releases; a reviewer spends about {daysLabel(info.effort_days)} per round (fitted). A PR&apos;s pool is
        its first sig/* label. Reviewers are counted per pool, never per person.
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="border-b border-slate-200">
            <tr>
              <th className={TH}>Pool</th>
              <th className={TH}>Reviewers now</th>
              <th className={TH}>New PRs / week</th>
              <th className={TH}>Open PRs</th>
              <th className={TH}>First review wait</th>
              <th className={TH}>Follow-up wait</th>
              <th className={TH}>PRs measured</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {poolsByLoad(info.pools).map((p) => (
              <tr key={p.pool}>
                <td className="py-3 pr-4 font-semibold text-slate-900">{poolName(p.pool)}</td>
                <td className="py-3 pr-4">{p.reviewers_now}</td>
                <td className="py-3 pr-4">{p.arrivals_per_week}</td>
                <td className="py-3 pr-4">{p.open_prs_now}</td>
                <td className="py-3 pr-4">{p.first_wait_median_days === null ? "—" : `${p.first_wait_median_days.toFixed(2)} d`}</td>
                <td className="py-3 pr-4">{p.follow_wait_median_days === null ? "—" : `${p.follow_wait_median_days.toFixed(2)} d`}</td>
                <td className="py-3 pr-4">{p.prs_measured.toLocaleString("en-US")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function OutcomeCard({ title, o, horizon, scenario }: { title: string; o: PoolOutcome | null; horizon: string; scenario?: boolean }) {
  const merged = o ? mergedLine(o, horizon) : null;
  const tone = scenario ? "border-indigo-300 bg-indigo-50 text-action" : "border-slate-100 bg-slate-50 text-slate-600";
  return (
    <div className={`rounded-xl border p-5 ${tone}`}>
      <p className="text-sm">{title}</p>
      <p className={`mt-2 font-heading text-4xl font-bold ${scenario ? "text-action" : "text-slate-900"}`}>{merged ? merged.big : "—"}</p>
      <p className="mt-1 text-sm">{merged ? merged.line : "Running the simulator…"}</p>
      <p className="mt-3 text-sm">
        Median review wait <strong>{o?.review_wait_days ? daysLabel(o.review_wait_days.median) : "—"}</strong>
        {o?.review_wait_days && <span className="opacity-75"> ({daysLabel(o.review_wait_days.low)}–{daysLabel(o.review_wait_days.high)})</span>}
      </p>
    </div>
  );
}

/** Words the run for the selected pool. Model output, never a guarantee. */
function runNote(sim: Simulation, pool: string, lever: string): string {
  const pick = (o: Simulation["baseline"]) => (pool === "all" ? o.total : o.pools.find((p) => p.pool === pool)) ?? null;
  const b = pick(sim.baseline);
  const s = pick(sim.scenario);
  if (!b || !s) return "";
  const wait = simDelta(b.review_wait_days, s.review_wait_days, "days", true);
  const merged = simDelta(b.merged, s.merged, "count", false);
  const where = pool === "all" ? "across all pools" : `in ${poolName(pool)}`;
  const parts = [
    b.review_wait_days && s.review_wait_days ? `median review wait goes from ${daysLabel(b.review_wait_days.median)} to ${daysLabel(s.review_wait_days.median)}` : null,
    b.merged && s.merged ? `PRs merged by ${sim.horizon_label} from ${Math.round(b.merged.median)} to ${Math.round(s.merged.median)}` : null,
  ].filter(Boolean);
  const noise = (wait?.overlaps ?? true) && (merged?.overlaps ?? true) ? " The ranges overlap, so the difference may be noise." : "";
  return `Model output: with ${lever} ${where}, ${parts.join(", and ")}.${noise}`;
}

export function Simulator({ release }: { release: string }) {
  const me = useMe();
  const canAct = me?.approver ?? false;
  const [info, setInfo] = useState<SimulatorInfo | null>(null);
  const [pool, setPool] = useState("");
  const [lever, setLever] = useState<LeverId>("reviewers");
  const [name, setName] = useState("");
  const [sim, setSim] = useState<Simulation | null>(null);
  const [saved, setSaved] = useState<SavedScenario[]>([]);
  const [picked, setPicked] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const loadSaved = useCallback(() => updatesRequest<SavedScenario[]>(`/releases/${release}/scenarios`).then(setSaved), [release]);

  useEffect(() => {
    let cancelled = false;
    updatesRequest<SimulatorInfo>(`/releases/${release}/simulator`)
      .then((d) => {
        if (cancelled) return;
        setInfo(d);
        setPool(poolsByLoad(d.pools)[0]?.pool ?? "");
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    loadSaved().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [release, loadSaved]);

  const settings: ScenarioSettings = useMemo(() => ({ ...leverSettings(lever, pool), name: name.trim() }), [lever, pool, name]);
  const body = useMemo(() => JSON.stringify({ ...settings, name: settings.name || "scenario" }), [settings]);

  // Run baseline vs scenario whenever the pool or lever changes (deterministic, no AI).
  useEffect(() => {
    if (!info || !pool) return;
    let cancelled = false;
    const t = setTimeout(() => {
      setBusy(true);
      setRunError(null);
      updatesRequest<Simulation>(`/releases/${release}/simulate`, { method: "POST", body: JSON.stringify({ ...leverSettings(lever, pool), name: "scenario" }) })
        .then((r) => !cancelled && setSim(r))
        .catch((e: Error) => !cancelled && setRunError(e.message))
        .finally(() => !cancelled && setBusy(false));
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [info, pool, lever, release]);

  async function save() {
    setBusy(true);
    setRunError(null);
    try {
      const row = await updatesRequest<SavedScenario>(`/releases/${release}/scenarios`, { method: "POST", body });
      setSim(row.result);
      setName("");
      await loadSaved();
    } catch (e) {
      setRunError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const compared = useMemo(() => picked.map((id) => saved.find((s) => s.id === id)).filter(Boolean) as SavedScenario[], [picked, saved]);

  if (error && !info) {
    // No calibration for this release (no earlier release to learn from) is not a failure (#60).
    if (error.startsWith("No simulator")) return <EmptyState title="No simulator for this release" body={error} />;
    return <ErrorState title="Decision Studio could not be loaded" detail={error} />;
  }
  if (!info) return <LoadingState label="Loading the simulator…" />;

  const pools = poolsByLoad(info.pools);
  const leverInfo = STUDIO_LEVERS.find((l) => l.id === lever) ?? STUDIO_LEVERS[0];
  const target = lever === "arrival" ? "all" : pool;
  const pick = (o: Simulation["baseline"] | undefined) => (o ? (target === "all" ? o.total : (o.pools.find((p) => p.pool === target) ?? null)) : null);
  const sources = info.source_releases.map(rel);
  const calibrated = sources.length > 1 ? `${sources[0]}–${sources[sources.length - 1]}` : (sources[0] ?? "");
  const notes = scenarioNotes(settings);

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-heading text-2xl font-semibold">Simulate and decide before you commit people or money</h2>
        <p className="mt-1 max-w-3xl text-slate-600">
          Pick a reviewer pool and one change, and see what would happen next to what happens today. Nothing changes for real; inputs are measured from real review history.
        </p>
      </div>
      <Banner info={info} releaseKey={info.release} />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <section className="rounded-2xl border border-slate-200 bg-white p-6">
          <h3 className="font-heading text-lg font-semibold">1 · Choose a reviewer pool</h3>
          <ul className="mt-3 max-h-[300px] space-y-2 overflow-y-auto pr-1" aria-label="Reviewer pools, most loaded first">
            {pools.map((p) => {
              const on = p.pool === pool;
              return (
                <li key={p.pool}>
                  <button type="button" aria-pressed={on} onClick={() => setPool(p.pool)}
                    className={`w-full rounded-xl border px-4 py-3 text-left ${on ? "border-action bg-indigo-50" : "border-slate-200 hover:border-slate-300"}`}>
                    <span className="block font-semibold text-slate-900">{poolName(p.pool)}</span>
                    <span className="block text-sm text-slate-600">
                      {p.reviewers_now} reviewer{p.reviewers_now === 1 ? "" : "s"} · {p.arrivals_per_week} new PRs/week · {p.open_prs_now} open
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          <h3 className="mt-6 font-heading text-lg font-semibold">2 · Pull one lever</h3>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {STUDIO_LEVERS.map((l) => (
              <button key={l.id} type="button" aria-pressed={l.id === lever} onClick={() => setLever(l.id)}
                className={`min-h-12 rounded-xl border px-4 text-left text-sm font-semibold ${l.id === lever ? "border-action bg-indigo-50 text-slate-900" : "border-slate-200 text-slate-800 hover:border-slate-300"}`}>
                {l.label}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-500">AI first-pass review and cutting features are not in the model yet.</p>
          <p className="mt-4 text-xs leading-5 text-slate-500">
            Calibrated on {calibrated}, data to {shortYear(info.data_until)} · {info.replications} seeded runs · horizon: {info.horizon_label}, {short(info.horizon_at)}.
          </p>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-heading text-lg font-semibold">3 · Baseline vs scenario · {target === "all" ? "All pools" : poolName(target)}</h3>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
              {busy ? "Running…" : info.validated ? "Model output" : "Model output · not validated"}
            </span>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <OutcomeCard title="Baseline · today's staffing" o={pick(sim?.baseline)} horizon={sim?.horizon_label ?? info.horizon_label} />
            <OutcomeCard title={`Scenario · ${leverInfo.scenario}`} o={pick(sim?.scenario)} horizon={sim?.horizon_label ?? info.horizon_label} scenario />
          </div>
          {sim && !busy && <p className="mt-4 rounded-xl bg-ink px-5 py-4 text-sm leading-6 text-white">{runNote(sim, target, leverInfo.scenario)}</p>}
          {runError && <p className="mt-3 text-sm text-critical">{runError}</p>}
          {notes.length > 0 && <p className="mt-3 text-xs text-slate-500">Scenario: {notes.map((n) => n.replace(/^sig\/[\w-]+: /, "")).join(" · ")}</p>}
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <input placeholder="Scenario name" aria-label="Scenario name" value={name} maxLength={128} onChange={(e) => setName(e.target.value)}
              className="min-h-11 rounded-lg border border-slate-300 px-3 text-sm" />
            <button type="button" onClick={save} disabled={busy || !name.trim() || !canAct}
              title={canAct ? undefined : "Sign in as an approver to save scenarios"}
              className="inline-flex min-h-11 items-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50">
              Save scenario
            </button>
            <a href="#saved" className="inline-flex min-h-11 items-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50">
              Compare saved
            </a>
          </div>
          {!canAct && <p className="mt-2 text-xs text-slate-500">Saving needs an approver sign-in. Running is open to everyone.</p>}
        </section>
      </div>

      <Assumptions info={info} />

      {sim && (
        <details className="group rounded-2xl border border-slate-200 bg-white">
          <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between px-6 text-sm font-semibold text-slate-800">
            <span>Every pool, baseline vs scenario · until {sim.horizon_label}</span>
            <span aria-hidden className="text-slate-400 group-open:rotate-180">▾</span>
          </summary>
          <div className="border-t border-slate-100 p-4"><Results sim={sim} onlyChanged={false} /></div>
        </details>
      )}

      <section id="saved" className="scroll-mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="font-heading text-xl font-semibold">Saved scenarios</h2>
        {saved.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">None yet. Name a scenario and choose &quot;Save scenario&quot;.</p>
        ) : (
          <ul className="mt-2 divide-y text-sm">
            {saved.map((s) => (
              <li key={s.id} className="flex min-h-11 items-center gap-3 py-1.5">
                <input type="checkbox" checked={picked.includes(s.id)} aria-label={`Compare ${s.name}`}
                  onChange={(e) => setPicked((p) => (e.target.checked ? [...p.filter((x) => x !== s.id), s.id].slice(-2) : p.filter((x) => x !== s.id)))} />
                <span className="font-medium">{s.name}</span>
                <span className="text-slate-500">{formatUtc(s.created_at)}</span>
                <button type="button" onClick={() => setSim(s.result)} className="ml-auto text-action hover:underline">Show</button>
              </li>
            ))}
          </ul>
        )}
        {compared.length === 2 && <div className="mt-3"><Compare a={compared[0]} b={compared[1]} /></div>}
        {saved.length > 1 && compared.length < 2 && <p className="mt-2 text-xs text-slate-500">Tick two scenarios to compare them.</p>}
        <p className="mt-3 text-xs text-slate-500">
          Decisions go into the <Link href="./update" className="text-action hover:underline">executive update</Link> only after a person approves it.
        </p>
      </section>
    </div>
  );
}
