import { afterEach, describe, expect, it, vi } from "vitest";
import { confirmRaid, editRaid, fetchRaid, fetchRaidQueue, fetchRaidSummary, rejectRaid, type RaidItem } from "./api-raid";

afterEach(() => vi.unstubAllGlobals());

// docs/api/raid-contract.md examples. The queue item adds the fixture's merge suggestion.
const source = { kind: "meeting" as const, title: "Synthetic release-team meeting (fixture, not real notes)", url: null, date: "2026-11-10T17:00:00Z", synthetic: true };
const item = (over: Partial<RaidItem>): RaidItem => ({
  item_id: 1, raid_id: "K8S-R-001", workstream: "K8S", type: "risk",
  title: "Main PR for enhancement #6395 may miss Code Freeze",
  quote: "Synthetic: the main PR for #6395 still needs an approver from SIG Storage.",
  source, owner: "SIG Storage", status: "open", review: "confirmed",
  links: [{ kind: "feature", ref: "kubernetes/enhancements#6395", method: "explicit_key", status: "verified" }],
  merge_suggestion: null, created_at: "2026-11-10T17:00:00Z", updated_at: "2026-11-10T17:00:00Z", ...over,
});
const wrap = (items: RaidItem[]) => ({ project: "kubernetes", release: "v1.38", as_of: "2026-11-25T21:00:00Z", synthetic: true, items });

function stub(body: unknown) {
  const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () => new Response(JSON.stringify(body), { status: 200 }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("RAID contract", () => {
  it("keeps synthetic, review, the quote and the merge suggestion", async () => {
    stub(wrap([item({})]));
    const tracker = await fetchRaid("kubernetes", "v1.38");
    expect(tracker.synthetic).toBe(true);
    expect(tracker.items[0]).toMatchObject({ raid_id: "K8S-R-001", review: "confirmed" });
    expect(tracker.items[0].quote).toBe(item({}).quote);
    expect(tracker.items[0].links[0].status).toBe("verified");

    stub(wrap([item({ item_id: 4, raid_id: null, owner: null, review: "suggested", links: [], quote: "Synthetic: node e2e has been flaky all week.", title: "CI flakes on the node e2e job", merge_suggestion: { into_item_id: 4, reason: "Same CI job and the same week as item 4." } })]));
    const queue = await fetchRaidQueue("kubernetes", "v1.38");
    expect(queue.items[0]).toMatchObject({ raid_id: null, review: "suggested" });
    expect(queue.items[0].merge_suggestion?.reason).toContain("Same CI job");

    stub({
      project: "kubernetes", release: "v1.38", as_of: "2026-11-25T21:00:00Z", synthetic: true,
      by_type: ["risk", "action", "issue", "decision", "question"].map((type) => ({ type, suggested: type === "risk" ? 2 : 0, open: type === "risk" || type === "decision" ? 1 : 0, in_progress: 0, closed: type === "action" ? 1 : 0, superseded: 0, rejected: type === "question" ? 1 : 0 })),
      risks_without_owner: 0, waiting_for_review: 2, sources: 1,
    });
    expect(await fetchRaidSummary("kubernetes", "v1.38")).toMatchObject({ synthetic: true, risks_without_owner: 0, waiting_for_review: 2 });
  });

  it("confirms, edits and rejects through /api/act, and never sends the quote", async () => {
    const fetch = stub({ ...item({ item_id: 4, raid_id: "K8S-R-002", review: "confirmed" }) });
    expect((await confirmRaid(4, "Owner to be assigned in the next meeting.")).raid_id).toBe("K8S-R-002");
    expect(String(fetch.mock.calls[0][0])).toBe("/api/act/raid/4/confirm");
    await editRaid(4, { title: "Node e2e flakes", type: "issue", owner: "SIG Node", status: "in_progress" });
    const edit = JSON.parse(String(fetch.mock.calls[1][1]?.body)) as Record<string, unknown>;
    expect(edit).toEqual({ title: "Node e2e flakes", type: "issue", owner: "SIG Node", status: "in_progress" });
    expect(edit).not.toHaveProperty("quote");
    await rejectRaid(4, "Not a release risk.");
    expect(String(fetch.mock.calls[2][0])).toBe("/api/act/raid/4/reject");
  });
});
