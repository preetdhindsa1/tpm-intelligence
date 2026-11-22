// Typed client for the FastAPI service. Shapes mirror api/schemas.py.

export type Flag = { code: string; severity: "info" | "warning" | "critical"; message: string; facts: Record<string, unknown> };

export type Odds = {
  status: "forecast" | "after_freeze" | "no_freeze_date" | "not_in_release";
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
};

export type VerifiedClaim = { text: string; type: string; refs: string[]; value: unknown };

export type RiskNote = {
  status: "not_at_risk" | "fresh" | "reused" | "stale" | "paused" | "failed";
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

/** Browser-side calls for the update page (POST/PATCH need the public URL). */
export async function updatesRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${publicApiUrl}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}
