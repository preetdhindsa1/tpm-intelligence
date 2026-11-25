"use client";

// What-if simulator (ADR-0012). Every number comes from the API's simulator; this page
// only shows it. Baseline is always next to the scenario, and results are ranges.
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
  type SimPool,
} from "@/lib/api";
import { daysLabel, errorPct, formatUtc, rangeLabel, simDelta, type SimDelta } from "@/lib/format";
import { LEVERS, scenarioNotes, type LeverId } from "@/lib/studio";

const LOW_EFFORT_DAYS = 0.03; // the fit's lower bound is 0.02 days (simulator/replay.py)
const NO_CHANGE: PoolChange = { reviewers: 0, new_reviewers: 0, ramp_weeks: 0, interruption: 0 };

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

function NotValidated({ info }: { info: SimulatorInfo }) {
  const v = info.validation;
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
      <p className="font-semibold">Not validated: do not rely on these what-ifs.</p>
      <p className="mt-1">
        Replaying past releases with their real staffing, the simulator did not match every real median within the ±
        {Math.round((v.tolerance ?? 0.2) * 100)}% allowed:
      </p>
      <ul className="mt-1 list-disc pl-5">
        {v.releases.map((r) => (
          <li key={r.release}>
            {r.release.replace("kubernetes:", "")}:{" "}
            {r.checks.map((c) => `${c.name.replace(" (days)", "")} ${errorPct(c.error)} ${c.passed ? "(pass)" : "(fail)"}`).join(", ")}
          </li>
        ))}
        {v.releases.length === 0 && <li>{v.reason ?? "no validation run"}</li>}
      </ul>
      {info.effort_days <= LOW_EFFORT_DAYS && (
        <p className="mt-1">
          The fitted reviewer time per round is at its lower limit ({daysLabel(info.effort_days)}), so in this model reviewer
          capacity has very little effect: adding or removing reviewers moves waits less than it likely would in reality.
        </p>
      )}
      <p className="mt-1">Details: ADR-0012{v.source_file ? ` · ${v.source_file}` : ""}.</p>
    </div>
  );
}

function Assumptions({ info }: { info: SimulatorInfo }) {
  return (
    <section className="rounded-lg border bg-white p-4 text-sm">
      <h2 className="font-medium text-slate-800">Measured assumptions</h2>
      <ul className="mt-2 space-y-0.5 text-slate-600">
        <li>
          Measured on {info.source_releases.map((r) => r.replace("kubernetes:", "")).join(", ")} (data until{" "}
          {formatUtc(info.data_until)}), calibration #{info.calibration_id} fitted {formatUtc(info.calibrated_at)}.
        </li>
        <li>
          Starts from the {info.pools.reduce((n, p) => n + p.open_prs_now, 0)} open PRs of this release now ({formatUtc(info.as_of)}) and runs
          until {info.horizon_label} ({formatUtc(info.horizon_at)}). New PRs arrive at the measured weekly rate.
        </li>
        <li>
          Each PR follows a real PR&apos;s review path from the source releases. A reviewer spends about {daysLabel(info.effort_days)} per
          round (fitted). Ranges are the 10th–90th percentile of {info.replications} seeded runs.
        </li>
        <li>A PR&apos;s pool is its first sig/* label in sorted order. Reviewers are counted per pool, never per person.</li>
      </ul>
      <table className="mt-3 w-full text-left text-xs">
        <thead className="text-slate-500">
          <tr>
            <th className="py-1">Pool</th>
            <th>PRs measured</th>
            <th>New PRs / week</th>
            <th>Reviewers / week (source)</th>
            <th>Reviewers now</th>
            <th>Open PRs now</th>
            <th>Median wait, first / later round</th>
          </tr>
        </thead>
        <tbody>
          {info.pools.map((p) => (
            <tr key={p.pool} className="border-t">
              <td className="py-1 font-medium">{p.pool}</td>
              <td>{p.prs_measured}</td>
              <td>{p.arrivals_per_week}</td>
              <td>{p.reviewers_per_week_source}</td>
              <td>{p.reviewers_now}</td>
              <td>{p.open_prs_now}</td>
              <td>
                {p.first_wait_median_days === null ? "—" : daysLabel(p.first_wait_median_days)} /{" "}
                {p.follow_wait_median_days === null ? "—" : daysLabel(p.follow_wait_median_days)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Levers({
  pools,
  pool,
  lever,
  settings,
  onPool,
  onLever,
  onChange,
  onArrival,
  onReset,
}: {
  pools: SimPool[];
  pool: string;
  lever: LeverId;
  settings: ScenarioSettings;
  onPool: (pool: string) => void;
  onLever: (lever: LeverId) => void;
  onChange: (pool: string, field: keyof PoolChange, value: number) => void;
  onArrival: (value: number) => void;
  onReset: () => void;
}) {
  const row = pools.find((p) => p.pool === pool) ?? pools[0];
  const change = (row && settings.pools[row.pool]) || NO_CHANGE;
  const notes = scenarioNotes(settings);
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex min-w-48 flex-col">
          <span className="text-xs text-slate-500">Pool</span>
          <select className="min-h-11 rounded border px-2" value={row?.pool ?? ""} disabled={lever === "arrival" || !row} onChange={(e) => onPool(e.target.value)}>
            {pools.map((p) => (
              <option key={p.pool} value={p.pool}>{p.pool}</option>
            ))}
          </select>
        </label>
        <label className="flex min-w-64 flex-col">
          <span className="text-xs text-slate-500">Lever</span>
          <select className="min-h-11 rounded border px-2" value={lever} onChange={(e) => onLever(e.target.value as LeverId)}>
            {LEVERS.map((item) => (
              <option key={item.id} value={item.id}>{item.label}</option>
            ))}
          </select>
        </label>
        <button type="button" onClick={onReset} className="inline-flex min-h-11 items-center rounded border px-3 text-slate-700 hover:bg-slate-50">
          Reset to baseline
        </button>
      </div>
      {lever === "arrival" && (
        <label className="flex max-w-sm flex-col">
          <span className="text-xs text-slate-500">Applies to every pool · ×{settings.arrival_multiplier.toFixed(1)}</span>
          <input type="range" min={0.5} max={2} step={0.1} value={settings.arrival_multiplier} onChange={(e) => onArrival(Number(e.target.value))} />
        </label>
      )}
      {lever === "reviewers" && row && (
        <label className="flex flex-col">
          <span className="text-xs text-slate-500">{row.pool} has {row.reviewers_now} reviewers now</span>
          <input className="w-24 min-h-11 rounded border px-2" type="number" min={-row.reviewers_now} max={50} value={change.reviewers} onChange={(e) => onChange(row.pool, "reviewers", Number(e.target.value))} />
        </label>
      )}
      {lever === "new_reviewers" && row && (
        <div className="flex flex-wrap gap-4">
          <label className="flex flex-col">
            <span className="text-xs text-slate-500">New reviewers</span>
            <input className="w-24 min-h-11 rounded border px-2" type="number" min={0} max={50} value={change.new_reviewers} onChange={(e) => onChange(row.pool, "new_reviewers", Number(e.target.value))} />
          </label>
          <label className="flex flex-col">
            <span className="text-xs text-slate-500">Ramp-up (weeks)</span>
            <input className="w-24 min-h-11 rounded border px-2 disabled:bg-slate-50" type="number" min={0} max={52} disabled={change.new_reviewers === 0} value={change.ramp_weeks} onChange={(e) => onChange(row.pool, "ramp_weeks", Number(e.target.value))} />
          </label>
        </div>
      )}
      {lever === "interruption" && row && (
        <label className="flex max-w-sm flex-col">
          <span className="text-xs text-slate-500">{row.pool} · {Math.round(change.interruption * 100)}% of reviewer time</span>
          <input type="range" min={0} max={0.9} step={0.05} value={change.interruption} onChange={(e) => onChange(row.pool, "interruption", Number(e.target.value))} />
        </label>
      )}
      {notes.length > 0 && (
        <div aria-live="polite">
          <p className="text-xs font-medium text-slate-700">Changes in this scenario</p>
          <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
            {notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Illustrative() {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {["Baseline", "Scenario"].map((title) => (
        <section key={title} className="rounded-lg border bg-white p-4">
          <h2 className="font-semibold text-slate-800">{title}</h2>
          <p className="mt-1 text-sm text-slate-600">Illustrative until you run the simulator. No scenario numbers yet.</p>
        </section>
      ))}
    </div>
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
      <table className="w-full text-left text-sm [&_td]:px-3 [&_th]:px-3">
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
      </table>
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
      <table className="w-full text-left text-sm">
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
      </table>
    </div>
  );
}

export function Simulator({ release }: { release: string }) {
  const me = useMe();
  const canAct = me?.approver ?? false;
  const [info, setInfo] = useState<SimulatorInfo | null>(null);
  const [settings, setSettings] = useState<ScenarioSettings>({ name: "", pools: {}, arrival_multiplier: 1 });
  const [sim, setSim] = useState<Simulation | null>(null);
  const [saved, setSaved] = useState<SavedScenario[]>([]);
  const [picked, setPicked] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [onlyChanged, setOnlyChanged] = useState(false);
  const [lever, setLever] = useState<LeverId>("reviewers");
  const [pool, setSelectedPool] = useState("");

  const loadSaved = useCallback(
    () => updatesRequest<SavedScenario[]>(`/releases/${release}/scenarios`).then(setSaved),
    [release],
  );

  useEffect(() => {
    let cancelled = false;
    updatesRequest<SimulatorInfo>(`/releases/${release}/simulator`)
      .then((d) => {
        if (cancelled) return;
        // Alphabetical, with the shared "other" pool last.
        const pools = [...d.pools].sort((a, b) => Number(a.pool === "other") - Number(b.pool === "other") || a.pool.localeCompare(b.pool));
        setInfo({ ...d, pools });
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    loadSaved().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [release, loadSaved]);

  function setPoolChange(pool: string, field: keyof PoolChange, value: number) {
    setSettings((s) => ({ ...s, pools: { ...s.pools, [pool]: { ...(s.pools[pool] ?? NO_CHANGE), [field]: value } } }));
  }

  function body(): ScenarioSettings {
    const pools = Object.fromEntries(Object.entries(settings.pools).filter(([, c]) => changed(c)));
    return { ...settings, pools };
  }

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setSim(await updatesRequest<Simulation>(`/releases/${release}/simulate`, { method: "POST", body: JSON.stringify(body()) }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const row = await updatesRequest<SavedScenario>(`/releases/${release}/scenarios`, {
        method: "POST",
        body: JSON.stringify(body()),
      });
      setSim(row.result);
      await loadSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function load(s: SavedScenario) {
    setSettings({ ...s.settings, name: "" });
    setSim(s.result);
  }

  const compared = useMemo(() => picked.map((id) => saved.find((s) => s.id === id)).filter(Boolean) as SavedScenario[], [picked, saved]);

  if (error && !info) {
    // No calibration for this release (no earlier release to learn from) is not a failure (#60).
    if (error.startsWith("No simulator")) return <EmptyState title="No simulator for this release" body={error} />;
    return <ErrorState title="Decision Studio could not be loaded" detail={error} />;
  }
  if (!info) return <LoadingState label="Loading the simulator…" />;

  return (
    <div className="space-y-4">
      {!info.validated && <NotValidated info={info} />}
      <Assumptions info={info} />

      <div className="rounded-lg border bg-white p-4">
        <Levers
          pools={info.pools}
          pool={pool || info.pools[0]?.pool || ""}
          lever={lever}
          settings={settings}
          onPool={setSelectedPool}
          onLever={setLever}
          onChange={setPoolChange}
          onArrival={(value) => setSettings((s) => ({ ...s, arrival_multiplier: value }))}
          onReset={() => setSettings((s) => ({ ...s, pools: {}, arrival_multiplier: 1 }))}
        />
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <button
            onClick={run}
            disabled={busy}
            className="rounded bg-action px-3 py-1.5 font-medium text-white hover:bg-action/90 disabled:opacity-50"
          >
            {busy ? "Running…" : "Run vs baseline"}
          </button>
          <input
            placeholder="Scenario name"
            value={settings.name}
            maxLength={128}
            onChange={(e) => setSettings((s) => ({ ...s, name: e.target.value }))}
            className="rounded border px-2 py-1.5"
          />
          <button
            onClick={save}
            disabled={busy || !settings.name.trim() || !canAct}
            title={canAct ? undefined : "Sign in as an approver to save scenarios"}
            className="rounded border px-3 py-1.5 font-medium text-action hover:bg-indigo-50 disabled:opacity-50"
          >
            Run and save
          </button>
          {error && <span className="text-rose-700">{error}</span>}
        </div>
      </div>

      {!sim && <Illustrative />}
      {sim && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">
              Baseline vs {sim.scenario.scenario.name === "scenario" ? "scenario" : sim.scenario.scenario.name} · until {sim.horizon_label}
            </h2>
            <label className="text-sm text-slate-600">
              <input type="checkbox" checked={onlyChanged} onChange={(e) => setOnlyChanged(e.target.checked)} /> Only changed pools
            </label>
          </div>
          <Results sim={sim} onlyChanged={onlyChanged} />
        </div>
      )}

      <div className="rounded-lg border bg-white p-4">
        <h2 className="text-lg font-semibold">Saved scenarios</h2>
        {saved.length === 0 ? (
          <p className="text-sm text-slate-500">None yet. Name a scenario and choose &quot;Run and save&quot;.</p>
        ) : (
          <ul className="mt-2 divide-y text-sm">
            {saved.map((s) => (
              <li key={s.id} className="flex items-center gap-3 py-1.5">
                <input
                  type="checkbox"
                  checked={picked.includes(s.id)}
                  onChange={(e) =>
                    setPicked((p) => (e.target.checked ? [...p.filter((x) => x !== s.id), s.id].slice(-2) : p.filter((x) => x !== s.id)))
                  }
                  aria-label={`Compare ${s.name}`}
                />
                <span className="font-medium">{s.name}</span>
                <span className="text-slate-500">
                  {formatUtc(s.created_at)} · {s.created_by.replace("user:", "")}
                </span>
                <button onClick={() => load(s)} className="ml-auto text-action hover:underline">
                  Load
                </button>
              </li>
            ))}
          </ul>
        )}
        {compared.length === 2 && (
          <div className="mt-3">
            <Compare a={compared[0]} b={compared[1]} />
          </div>
        )}
        {saved.length > 1 && compared.length < 2 && <p className="mt-2 text-xs text-slate-500">Tick two scenarios to compare them.</p>}
      </div>
    </div>
  );
}
