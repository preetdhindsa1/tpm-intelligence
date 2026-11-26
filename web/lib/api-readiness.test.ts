import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchPatterns, fetchReadiness, fetchRetro, fetchSaidVsShowed, postDecision, replayDay, type Retro } from "./api-readiness";

afterEach(() => vi.unstubAllGlobals());

const readiness = {
  project: "kubernetes", release: "v1.38", as_of: "2026-11-25T21:00:00Z", synthetic: true, verdict: "not_ready",
  criteria: [
    { id: "code_merged", name: "Code merged or excepted", status: "fail", detail: "Synthetic fixture: 2 features have a main PR that is not merged and has no exception.", count: 2, evidence: [{ text: "Synthetic fixture: Main PR #144232 is open.", ref: "feature:kubernetes/enhancements#5419", url: null }] },
    { id: "risks_owned", name: "Every open risk has an owner", status: "unknown", detail: "Synthetic fixture: No confirmed RAID risks yet; suggested items do not count.", count: null, evidence: [] },
  ],
  decisions: [{ decision: "no_go", note: "Two main PRs are open without an exception.", decided_by: "approver", decided_at: "2026-11-25T21:00:00Z", facts_as_of: "2026-11-25T21:00:00Z" }],
  summary: null, validated: false, validation_note: "Not validated: the readiness backtest has not run (ADR-0032).",
};

const slip = { feature_key: "kubernetes/enhancements#9001", title: "Synthetic fixture: dropped feature", pool: "sig/node", slip: "dropped" as const, slipped_at: "2026-11-17T12:00:00Z", first_warning_at: "2026-11-05T12:00:00Z", first_warning_flag: "late_main_pr", lead_time_days: 12 };
const retro: Retro = {
  project: "kubernetes", release: "v1.37", label: "Synthetic retro (fixture)", as_of: "2026-11-25T21:00:00Z", synthetic: true,
  sources: [{ kind: "snapshots", title: "Synthetic forecast snapshots", url: null, synthetic: true }],
  totals: { slips: 2, warned: 1, average_lead_time_days: 12, median_lead_time_days: 12 },
  slips: [slip, { ...slip, feature_key: "kubernetes/enhancements#9002", title: "Synthetic fixture: late exception", pool: "sig/storage", slip: "late_exception", slipped_at: "2026-11-20T12:00:00Z", first_warning_at: null, first_warning_flag: null, lead_time_days: null }],
};

function stub(body: unknown) {
  const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () => new Response(JSON.stringify(body), { status: 200 }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("readiness and retro contract", () => {
  it("reads the verdict, validated, unknown, and posts a decision through /api/act", async () => {
    const fetch = stub(readiness);
    const body = await fetchReadiness("v1.38");
    expect(body).toMatchObject({ synthetic: true, verdict: "not_ready", validated: false, summary: null });
    expect(body.criteria.map((c) => c.status)).toEqual(["fail", "unknown"]);
    expect(body.decisions[0].decided_by).toBe("approver");
    await postDecision("v1.38", "defer", "Wait for the two open main PRs.");
    expect(String(fetch.mock.calls[1][0])).toBe("/api/act/readiness/v1.38/decision");
    expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toEqual({ decision: "defer", note: "Wait for the two open main PRs." });
  });

  it("reads slips, said vs showed and patterns, and the real-retro fields when the API sends them", async () => {
    stub(retro);
    const body = await fetchRetro("kubernetes", "v1.37");
    expect(body).toMatchObject({ label: "Synthetic retro (fixture)", synthetic: true });
    expect(body.slips[1]).toMatchObject({ slip: "late_exception", first_warning_at: null });
    expect(body.totals.warned_landed).toBeUndefined();

    stub({ ...retro, synthetic: false, label: "Kubernetes v1.37, public retro", totals: { ...retro.totals, planned: 98, warned_landed: 47 }, slips: [{ ...slip, slip: "moved", moved_to: "v1.38" }] });
    const live = await fetchRetro("kubernetes", "v1.37");
    expect(live.label).toBe("Kubernetes v1.37, public retro");
    expect(live.totals).toMatchObject({ planned: 98, warned_landed: 47 });
    expect(live.slips[0].moved_to).toBe("v1.38");

    const row = { date: "2026-11-10T12:00:00Z", said: [{ item_id: 4, raid_id: null, type: "risk" as const, title: "Synthetic fixture: CI flakes on the node e2e job", review: "suggested" as const }], showed: [{ name: "features_at_risk", value: 11 }, { name: "critical_flags", value: 3 }] };
    stub({ project: "kubernetes", release: "v1.37", synthetic: true, rows: [row] });
    const said = await fetchSaidVsShowed("kubernetes", "v1.37");
    expect(said.rows[0].said[0].review).toBe("suggested");
    expect(replayDay(said.rows[0])).toBeNull();
    expect(replayDay({ ...row, showed: [...row.showed, { name: "replay_day", value: "2026-11-10" }] })).toBe("2026-11-10");

    stub({ project: "kubernetes", synthetic: true, min_group: 10, suppressed_groups: 4, patterns: [{ pool: "sig/node", pattern: "late_main_pr", text: "Synthetic fixture: main PRs opened in the last 14 days before Code Freeze", value: 0.4, n: 25, releases: ["v1.36", "v1.37"] }] });
    expect(await fetchPatterns("kubernetes")).toMatchObject({ suppressed_groups: 4, min_group: 10 });
  });
});
