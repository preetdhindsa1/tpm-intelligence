// AI-native PDLC page: GET /lab pod facts (docs/api/ux-v1-contract.md, ADR-0023 addendum 2).
// Every number comes from the API. This file only words them; it never computes a fact.
import { serverApiUrl } from "@/lib/api";

export type PodStatus = "held" | "broken" | "not_measured";
export type PodMember = {
  lane: string; kind: string; opened: number; merged: number; closed_unmerged: number; open: number;
  median_minutes_to_merge: number | null;
};
export type PodStage = {
  stage: string; rules: string; status: PodStatus; value: Record<string, number | null> | null; reason: string | null;
};
export type PodMetric = { metric: string; target: string; value: number | null; unit: string; reason: string | null };
export type PodRule = { rule: string; title: string; status: PodStatus; count: number | null; of: number | null };
export type Pod = { members: PodMember[]; no_lane: number; flow: PodStage[]; metrics: PodMetric[]; rules: PodRule[] };
export type PodLab = { as_of: string; n_pull_requests: number; n_merged: number; pod: Pod | null };

/** This repository's lab, with pod facts. Throws on HTTP errors so the page can say so. */
export async function fetchPodLab(): Promise<PodLab> {
  const res = await fetch(`${serverApiUrl}/lab?project=tpm-intelligence`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET /lab: HTTP ${res.status}`);
  return (await res.json()) as PodLab;
}

export const MEMBER_TEXT: Record<string, { name: string; does: string; never: string }> = {
  human: { name: "Human (owner) · harpreet", does: "Writes the contract and the hard parts",
           never: "Reviews every PR in review windows. Merges. Makes the release call." },
  claude: { name: "Claude Code · claude-agent", does: "Builds its lane, cross-reviews the others",
            never: "Never approves or merges. Never edits approved tests." },
  cursor: { name: "Cursor agent · cursor-agent", does: "Builds its lane, cross-reviews the others",
            never: "Same limits as Claude Code. Two open PRs at most." },
  dependabot: { name: "Dependabot · bot", does: "Opens dependency and security updates",
                never: "An agent checks each update; the human merges." },
};

export const STAGE_TEXT: Record<string, { name: string; rule: string }> = {
  contract: { name: "Contract", rule: "The human approves the spec and acceptance tests before any code is written. Every issue has a risk tier." },
  build: { name: "Build", rule: "Small PRs. Two open PRs per agent. Two agents do not change the same files at the same time." },
  cross_review: { name: "Cross-review", rule: "The other agent reviews every agent PR; both agents review the human's PRs." },
  ci: { name: "CI", rule: "Three red CI runs go to the human. An agent does not loop forever." },
  human_review: { name: "Human review", rule: "The human reviews twice a day at set times, by risk tier. A third review round means the contract is wrong." },
  merge: { name: "Merge", rule: "Agents never merge. Velocity is merged, kept and released changes, never PRs opened." },
  kept: { name: "Kept", rule: "Count changes that are merged, kept and released. Kept means not reverted within 30 days." },
};

const n = (v: number | null | undefined) => (v === null || v === undefined ? "?" : `${v}`);

/** The short value under a stage button. */
export function stageValue(s: PodStage): string {
  const v = s.value ?? {};
  if (s.status === "not_measured" && s.stage !== "merge" && s.stage !== "kept") return "Not measured";
  switch (s.stage) {
    case "build": return s.status === "held" ? "Held" : `${n(v.max_open_per_agent)} open at most`;
    case "cross_review": return `${n(v.cross_reviewed)} of ${n(v.agent_merged)}`;
    case "ci": return `${n(v.failing_head_check)} failing`;
    case "human_review":
      return v.approved_of ? `${n(v.approved)} of ${n(v.approved_of)} approved` : `${n(v.human_reviewed)} of ${n(v.merged)}`;
    case "merge": return v.median_minutes_to_merge == null ? "Not enough data yet" : `${v.median_minutes_to_merge} min median`;
    case "kept": return s.status === "not_measured" ? "TBD" : `${n(v.kept)} of ${n(v.eligible)}`;
    default: return s.status === "held" ? "Held" : "Broken";
  }
}

/** One sentence that says what the numbers mean, plus the API's reason when there is one. */
export function stageDetail(s: PodStage): string {
  const v = s.value ?? {};
  const parts: Record<string, string> = {
    build: `At most ${n(v.max_open_per_agent)} PRs were open at once in one agent lane. ${n(v.over_400_lines)} PRs went over 400 changed lines without a size exception. ${n(v.collisions)} open PRs collide on the same files.`,
    cross_review: `${n(v.cross_reviewed)} of ${n(v.agent_merged)} merged agent PRs had a review from the other agent before merge.`,
    ci: `${n(v.failing_head_check)} PRs have a failing check on their latest commit.`,
    human_review: `${v.approved_of ? `${n(v.approved)} of ${n(v.approved_of)} PRs merged since the pod rules started (24 Nov 2026) were approved by the human, who merges every PR. ` : ""}${n(v.human_reviewed)} of ${n(v.merged)} merged PRs also had a written human review or comment before merge. An agent comment without its marker line counts as human.`,
    merge: v.median_minutes_to_merge == null ? "" : `Median open to merge is ${v.median_minutes_to_merge} minutes.`,
    kept: s.status === "not_measured" ? "" : `${n(v.kept)} of ${n(v.eligible)} PRs merged 30+ days ago were not reverted.`,
  };
  return [parts[s.stage] ?? "", s.reason ?? ""].filter(Boolean).join(" ");
}

export const METRIC_NAME: Record<string, string> = {
  review_rounds_per_pr: "Review rounds per PR",
  first_pass_approval: "First-pass approval",
  open_to_merge: "Open → merge",
  three_plus_rounds: "PRs needing 3+ rounds",
  kept_rate_30d: "Kept rate (30 days)",
  human_review_load: "Human review load",
};

/** "9 min median", "12%", or the API's reason when the value is not known. */
export function metricValue(m: PodMetric): string {
  if (m.value === null) return m.reason ?? "TBD (not yet measured)";
  if (m.unit === "share") return `${Math.round(m.value * 100)}%`;
  if (m.unit === "minutes") return `${m.value} min median`;
  return `${m.value} ${m.unit}`;
}

/** "40 of 52 break it", "Held", or "Not measured yet". */
export function ruleValue(r: PodRule): string {
  if (r.status === "not_measured") return "Not measured yet";
  if (r.status === "held") return `Held · 0 of ${n(r.of)}`;
  return `${n(r.count)} of ${n(r.of)} break it`;
}

export function statusTone(status: PodStatus): string {
  if (status === "held") return "bg-healthy-bg text-healthy";
  if (status === "broken") return "bg-critical-bg text-critical";
  return "bg-slate-100 text-slate-700";
}

// The next-rule chooser describes what would become measurable. It shows no numbers.
export const NEXT_RULES = [
  { title: "R13 · Turn on cross-review", body: "Claude reviews Cursor's PRs, Cursor reviews Claude's, both review the human's.",
    effect: "Agent reviews are counted separately from human review (marker line), so the cross-review stage shows how many PRs another agent checked before the human looked." },
  { title: "R14 · Two human review windows", body: "Agents batch PRs for late morning and late afternoon.",
    effect: "A review queue forms between windows. Open → merge grows from minutes toward same-day, and that growth is the real cost of checking AI work." },
  { title: "R26 · Group Dependabot updates", body: "Weekly, grouped updates with an open-PR limit in dependabot.yml.",
    effect: "Fewer bot PRs and fewer closed unmerged. The Dependabot row shows the change." },
  { title: "R2 · Require review before merge", body: "Branch rules: a PR, passing CI and a recorded review.",
    effect: "The human-review stage fills in. Medians per lane appear after 5 merged PRs in that lane." },
];

/** Multi-agent development, in plain words (AI-native PDLC page). Rules are the pod's own (docs/pod/RULES.md). */
export const MULTI_AGENT = {
  title: "Multi-agent development: one person shipping with two AI agents",
  intro: [
    "Multi-agent development means more than one AI agent writes code on the same product, side by side with people. Here, Claude Code and Cursor each work in their own lane, a bot keeps dependencies current, and one human owns the plan and the merge button.",
    "Writing code is no longer the hard part. The hard part is keeping several fast writers from colliding, and checking their work before it ships. That is what this page measures.",
  ],
  points: [
    { id: "lanes", title: "Separate lanes", body: "The rule: each agent works from its own issues and branches (claude/, cursor/), with at most two open PRs at a time, so two agents do not change the same files at once." },
    { id: "cross", title: "Agents check each other", body: "The rule: every agent PR is reviewed by the other agent before the human looks. The review starts with a marker line, so it counts as an agent review, not a human one." },
    { id: "human", title: "A human decides", body: "The rule: agents never approve or merge. The owner reviews in set windows, by risk label, and presses merge." },
    { id: "measured", title: "Measured, not claimed", body: "Everything below comes from this repository's real pull requests: who opened them, who reviewed them, and how fast they merged." },
  ],
} as const;

/** The live check under a multi-agent point, from the pod flow. Null when the data has none. */
export function multiAgentFact(id: string, pod: Pod): string | null {
  const v = (stage: string) => pod.flow.find((s) => s.stage === stage)?.value ?? null;
  if (id === "lanes") {
    const b = v("build");
    return b?.max_open_per_agent == null ? null : `So far: at most ${b.max_open_per_agent} PRs open at once in one lane.`;
  }
  if (id === "cross") {
    const c = v("cross_review");
    return c?.agent_merged ? `So far: ${c.cross_reviewed ?? 0} of ${c.agent_merged} merged agent PRs had one.` : null;
  }
  if (id === "human") {
    const h = v("human_review");
    if (!h?.merged) return null;
    const approved = h.approved_of ? `${h.approved ?? 0} of ${h.approved_of} PRs merged since the rules started were approved by the human; ` : "";
    return `So far: ${approved}${h.human_reviewed ?? 0} of ${h.merged} merged PRs had a written human review.`;
  }
  return null;
}
