// Typed client for the FastAPI service. Shapes mirror api/schemas.py.
import type { Portfolio } from "@/lib/portfolio";

export type Flag = { code: string; severity: "info" | "warning" | "critical"; message: string; facts: Record<string, unknown> };

export type Odds = {
  status: "forecast" | "after_freeze" | "no_freeze_date" | "insufficient_history" | "not_in_release";
  validated: boolean;
  base_rate: number | null;
  raw_probability: number | null;
  probability: number | null;
  low: number | null;
  high: number | null;
  open_prs: string[];
  pr_on_time: Record<string, number>;
  new_pr_needed: number | null;
};

export type Release = {
  key: string;
  name: string;
  project: string;
  display_name: string;
  cycle_start_at: string | null;
  enhancements_freeze_at: string | null;
  code_freeze_at: string | null;
  release_at: string | null;
  features_in_release: number;
  features_ever_in_release: number;
  as_of: string;
  has_lab?: boolean;
  code_freeze_label?: string;
};

export type LabReport = {
  release: string;
  project: string;
  lanes_configured: boolean;
  as_of: string;
  n_pull_requests: number;
  n_merged: number;
  n_open: number;
  small_sample: boolean;
  buckets: { lane: string; opened: number; merged: number; still_open: number }[];
  approval_rate: number | null;
  approved_merged: number;
  median_hours_to_merge: number | null;
  arrivals: { week: string; lane: string; count: number }[];
  queue: { day: string; count: number }[];
  time_to_first_review_hours: number[];
  still_waiting: number;
  review_round_counts: number[];
  review_rounds_median: number | null;
  rework: number;
  ci_failures: number;
  collisions: { kind: string; pull_requests: string[]; paths: string[]; truncated: boolean }[];
  cap: {
    observed_max_open: number;
    held: number | null;
    scenario_max_open: number | null;
    comparable: boolean;
    assumption: string;
  };
  first_pass: {
    observed_median_hours: number | null;
    n: number;
    waiting: number;
    comparable: boolean;
    assumption: string;
  };
  size: {
    over_cap: number;
    extra_pull_requests: number | null;
    comparable: boolean;
    assumption: string;
  };
};

export type FeatureRow = {
  key: string;
  number: number;
  title: string;
  url: string | null;
  in_release: boolean;
  tracked: boolean;
  stage: string | null;
  teams: string[];
  odds: Odds;
  flags: Flag[];
  prs_total: number;
  prs_merged: number;
  prs_open: number;
  suggested_prs: number;
};

export type PullRequest = {
  key: string;
  url: string;
  title: string;
  state: string;
  created_at: string;
  merged_at: string | null;
  review_rounds: number;
  review_records: number;
  failing_checks: number;
  freeze_status: string;
  counts_for_release: boolean;
  is_main: boolean;
};

export type TimelineEntry = { at: string; kind: string; ref: string | null };

export type FeatureDetail = FeatureRow & {
  pull_requests: PullRequest[];
  suggested_pull_requests: string[];
  critical_path: string[];
  timeline: TimelineEntry[];
  assumptions: Record<string, unknown>;
  merge_date: MergeDate | null;
  merge_date_validation: { validated?: boolean; reason?: string };
};

export type Validation = { validated: boolean; reason: string; source_file: string | null };

export type FeaturesResponse = {
  release: Release;
  features: FeatureRow[];
  calibration: Record<string, unknown>;
  validation: Validation;
};

/** Server-side base URL (inside Docker the API is http://api:8000). */
export const serverApiUrl = process.env.API_URL ?? "http://localhost:8000";
/** Browser base URL for the SSE stream. */
export const publicApiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${serverApiUrl}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

export const api = {
  releases: () => get<Release[]>("/releases"),
  features: (release: string) => get<FeaturesResponse>(`/releases/${release}/features`),
  feature: (release: string, n: number) => get<FeatureDetail>(`/releases/${release}/features/${n}`),
  summary: (release: string) => get<Summary>(`/releases/${release}/summary`),
  simulator: (release: string) => get<SimulatorInfo>(`/releases/${release}/simulator`),
  mergeDates: (release: string) => get<MergeDates>(`/releases/${release}/merge-dates`),
  snapshots: (release: string) => get<Snapshots>(`/releases/${release}/snapshots`),
  dependencies: (release: string, includeRemoved = false) =>
    get<Dependencies>(`/releases/${release}/dependencies${includeRemoved ? "?include_removed=true" : ""}`),
  updates: (release: string) => get<ExecUpdate[]>(`/releases/${release}/updates`),
  portfolio: () => get<Portfolio>("/portfolio"),
  lab: (project: string, release?: string, cap = 2, lines = 400) => {
    const query = new URLSearchParams({ project, cap: String(cap), lines: String(lines) });
    if (release) query.set("release", release);
    return get<LabReport>(`/lab?${query}`);
  },
};

export type VerifiedClaim = { text: string; type: string; refs: string[]; value: unknown };

export type RiskNote = {
  status: "not_at_risk" | "fresh" | "reused" | "stale" | "paused" | "failed" | "sign_in_required";
  reason: string | null;
  claims: VerifiedClaim[];
  claims_removed: number;
  removed_by_reason: Record<string, number>;
  attempts: number;
  model: string | null;
  prompt_version: string | null;
  generated_at: string | null;
  cost_usd: number | null;
  odds_validated: boolean | null;
};

export type UpdateWarning = { section: string; text: string; reason: string; detail: string | null };

export type ExecUpdate = {
  id: number;
  release: string;
  status: "draft" | "approved" | "rejected";
  stale: boolean;
  header: {
    release: string | null;
    data_as_of: string | null;
    code_freeze_at: string | null;
    release_at: string | null;
    features_in_release: number | null;
    features_removed: number | null;
    features_at_risk: number | null;
    odds_validated: boolean;
  };
  sections: Record<string, VerifiedClaim[]>;
  word_count: number;
  claims_removed: number;
  removed: { text: string; reason: string | null; detail: string | null }[];
  trimmed_for_length: number;
  attempts: number;
  model: string;
  prompt_version: string;
  cost_usd: number;
  edited: boolean;
  warnings: UpdateWarning[];
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  approved_with_warnings: boolean;
  approved_while_stale: boolean;
  created_at: string;
  markdown: string;
};

export const SECTION_TITLES: Record<string, string> = {
  summary: "Summary",
  at_risk: "At risk",
  removed: "Removed at Code Freeze",
  asks: "Asks",
};

/**
 * Browser-side calls to the API, through the same-origin signed route (ADR-0016): the web
 * server adds the signed-in user's signature, and the API decides who may act.
 */
export async function updatesRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/act${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export type LinkSuggestion = {
  id: number;
  status: "suggested" | "confirmed" | "rejected";
  pull_request: string;
  pull_request_title: string | null;
  pull_request_url: string | null;
  pull_request_state: string | null;
  feature: string;
  feature_number: number | null;
  feature_title: string | null;
  pr_quote: string;
  feature_quote: string;
  shortlist_rank: number | null;
  shortlist_size: number | null;
  model: string;
  prompt_version: string;
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
};

export type LinkSuggestions = {
  release: string;
  counts: Record<string, number>;
  cost_usd: number;
  suggestions: LinkSuggestion[];
};

// ---- simulator (ADR-0012) ----

export type SimRange = { median: number; low: number; high: number };

export type PoolOutcome = {
  pool: string;
  reviewers: number | null;
  review_wait_days: SimRange | null;
  merged: SimRange | null;
  not_merged: SimRange | null;
};

export type PoolChange = { reviewers: number; new_reviewers: number; ramp_weeks: number; interruption: number };

export type ScenarioSettings = { name: string; pools: Record<string, PoolChange>; arrival_multiplier: number };

export type SimOutcome = { scenario: ScenarioSettings; pools: PoolOutcome[]; total: PoolOutcome };

export type SimCheck = { name: string; real: number | null; simulated: number | null; error: number | null; passed: boolean };

export type SimValidation = {
  passed: boolean;
  source_file?: string;
  measured_at?: string;
  tolerance?: number;
  reason?: string;
  releases: { release: string; passed: boolean; checks: SimCheck[] }[];
};

export type SimPool = {
  pool: string;
  prs_measured: number;
  arrivals_per_week: number;
  reviewers_per_week_source: number;
  reviewers_now: number;
  open_prs_now: number;
  first_wait_median_days: number | null;
  follow_wait_median_days: number | null;
  first_scale: number;
  later_scale: number;
};

export type SimulatorInfo = {
  release: string;
  validated: boolean;
  validation: SimValidation;
  calibration_id: number;
  calibrated_at: string;
  source_releases: string[];
  data_until: string;
  effort_days: number;
  as_of: string;
  horizon_at: string;
  horizon_label: string;
  replications: number;
  pools: SimPool[];
  note: string;
};

export type Simulation = {
  release: string;
  validated: boolean;
  calibration_id: number;
  source_releases: string[];
  as_of: string;
  horizon_at: string;
  horizon_label: string;
  replications: number;
  seed: number;
  baseline: SimOutcome;
  scenario: SimOutcome;
  seconds: number;
  note: string;
};

export type SavedScenario = {
  id: number;
  name: string;
  created_by: string;
  created_at: string;
  calibration_id: number;
  settings: ScenarioSettings;
  result: Simulation;
};

// ---- dashboard (ADR-0013) ----

export type Outcome =
  | "landed"
  | "landed_prs_after_freeze"
  | "landed_main_pr_open"
  | "readded_after_freeze"
  | "removed_after_freeze"
  | "removed_at_freeze"
  | "removed_before_freeze"
  | "too_early";

export type Summary = {
  release: string;
  as_of: string;
  phase: "before_freeze" | "after_freeze";
  features_in_release: number;
  features_ever: number;
  landed: number | null;
  removed_at_freeze: number;
  critical_features: number;
  open_linked_prs: number;
  unlinked_open_prs: number;
  outcomes: Partial<Record<Outcome, number>>;
  features: { key: string; number: number; title: string; outcome: Outcome; sigs: string[] }[];
};


// Feature-to-feature dependencies (api/schemas.py DependenciesOut).
export type DepPR = { key: string; number: number; title: string; url: string; state: string; is_main: boolean; freeze_status: string };
export type DepFeature = {
  key: string;
  number: number;
  title: string;
  url: string | null;
  sigs: string[];
  in_release: boolean;
  severity: string | null;
  flags: string[];
  outcome: Outcome;
  cluster: number | null;
  prs: DepPR[];
};
export type StatedDependency = { upstream: string; downstream: string; blocker: string; dependent: string };
export type Coupling = { a: string; b: string; shared_prs: string[]; stated: StatedDependency[] };
export type WaitingPR = { pr: string; pr_title: string; waits_on: string; waits_on_title: string; waits_on_state: string; features: string[] };
export type Dependencies = {
  release: string;
  as_of: string;
  include_removed: boolean;
  features: DepFeature[];
  pr_edges: { source: string; target: string; kind: string }[];
  couplings: Coupling[];
  clusters: string[][];
  waiting: WaitingPR[];
  sig_pairs: { a: string; b: string; features: number }[];
};

// Merge dates and the days-of-delay chart (api/schemas.py MergeDatesOut). Days are
// relative to Code Freeze.
export type MergeDate = {
  feature_key: string;
  status: "done" | "forecast" | "no_freeze_date" | "insufficient_history";
  done_day: number | null;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  by_freeze: number | null;
  by_release: number | null;
  cdf: [number, number, number, number][];
};
export type CurveFeature = {
  key: string;
  number: number;
  title: string;
  status: string;
  done_day: number | null;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  by_release: number | null;
};
export type MergeDates = {
  release: string;
  as_of: string;
  code_freeze_at: string | null;
  release_at: string | null;
  as_of_day: number | null;
  release_day: number | null;
  features: number;
  done_now: number;
  forecast: [number, number, number, number][];
  actual: [number, number][];
  items: CurveFeature[];
  validation: { validated?: boolean; reason?: string };
  note: string;
};

// Forecasts recorded daily, append-only (ADR-0015).
export type Snapshots = {
  release: string;
  current_model_version: string;
  runs: { snapshot_date: string; as_of: string; model_version: string; features: number }[];
};
