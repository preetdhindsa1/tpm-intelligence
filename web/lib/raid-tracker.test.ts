import { describe, expect, it } from "vitest";
import type { RaidHistoryEntry, RaidItem } from "./api-raid";
import { actorRole, oldestFirst, trackerRows } from "./raid-tracker";

const item = (over: Partial<RaidItem>): RaidItem => ({
  item_id: 1, raid_id: "K8S-R-001", workstream: "K8S", type: "risk", title: "A risk",
  quote: "Synthetic: the main PR for #6395 still needs an approver from SIG Storage.",
  source: { kind: "meeting", title: "notes", url: null, date: "2026-11-10T17:00:00Z", synthetic: true },
  owner: "SIG Storage", status: "open", review: "confirmed", links: [], merge_suggestion: null,
  created_at: "2026-11-10T17:00:00Z", updated_at: "2026-11-12T17:00:00Z", ...over,
});

const entry = (over: Partial<RaidHistoryEntry>): RaidHistoryEntry => ({
  at: "2026-11-10T17:00:00Z", actor: "extractor", action: "suggested", changes: {}, reason: null, ...over,
});

describe("RAID tracker", () => {
  const rows = [
    item({}),
    item({ item_id: 2, raid_id: "K8S-A-001", type: "action", status: "closed", review: "edited", workstream: "SIG" }),
    item({ item_id: 4, raid_id: null, review: "suggested" }),
    item({ item_id: 6, raid_id: null, review: "rejected", status: "superseded" }),
  ];

  it("filters by type, status and workstream, and drops suggested items", () => {
    expect(trackerRows(rows, { type: "", status: "", workstream: "" }).map((r) => r.item_id)).toEqual([1, 2]);
    expect(trackerRows(rows, { type: "action", status: "", workstream: "" }).map((r) => r.raid_id)).toEqual(["K8S-A-001"]);
    expect(trackerRows(rows, { type: "", status: "open", workstream: "K8S" })).toHaveLength(1);
    expect(trackerRows(rows, { type: "risk", status: "closed", workstream: "" })).toHaveLength(0);
  });

  it("orders history oldest first and shows the actor as a role", () => {
    const ordered = oldestFirst([
      entry({ at: "2026-11-10T18:00:00Z", actor: "approver", action: "confirmed" }),
      entry({ at: "2026-11-10T17:00:00Z" }),
    ]);
    expect(ordered.map((r) => r.action)).toEqual(["suggested", "confirmed"]);
    expect(actorRole("extractor")).toBe("extractor");
    expect(actorRole("approver")).toBe("approver");
    expect(actorRole("octocat")).toBe("approver");
  });
});
