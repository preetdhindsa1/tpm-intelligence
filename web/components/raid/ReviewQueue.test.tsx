import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RaidItem, RaidList, RaidSummary } from "@/lib/api-raid";
import { ReviewQueue } from "./ReviewQueue";

const viewer = vi.hoisted(() => ({ approver: false }));
const confirmRaid = vi.hoisted(() => vi.fn());

vi.mock("@/components/Me", () => ({
  useMe: () => ({ login: viewer.approver ? "approver" : null, signed_in: viewer.approver, approver: viewer.approver, mode: "test" }),
  ApproverNote: () => null,
}));
vi.mock("@/lib/api-raid", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-raid")>();
  return { ...actual, confirmRaid };
});

const item: RaidItem = {
  item_id: 4, raid_id: null, workstream: "K8S", type: "risk", title: "CI flakes on the node e2e job",
  quote: "Synthetic: node e2e has been flaky all week.",
  source: { kind: "meeting", title: "Synthetic release-team meeting (fixture, not real notes)", url: null, date: "2026-11-10T17:00:00Z", synthetic: true },
  owner: null, status: "open", review: "suggested", links: [],
  merge_suggestion: { into_item_id: 1, reason: "Same CI job and the same week as item 4." },
  created_at: "2026-11-10T17:00:00Z", updated_at: "2026-11-10T17:00:00Z",
};
const queue: RaidList = { project: "kubernetes", release: "v1.38", as_of: "2026-11-25T21:00:00Z", synthetic: true, items: [item] };
const summary: RaidSummary = {
  project: "kubernetes", release: "v1.38", as_of: "2026-11-25T21:00:00Z", synthetic: true,
  by_type: [{ type: "risk", suggested: 1, open: 1, in_progress: 0, closed: 0, superseded: 0, rejected: 0 }],
  risks_without_owner: 0, waiting_for_review: 1,
};

afterEach(cleanup);

beforeEach(() => {
  viewer.approver = false;
  confirmRaid.mockReset();
});

describe("RAID review queue", () => {
  it("shows the quote verbatim and hides actions from a reader", () => {
    render(<ReviewQueue queue={queue} summary={summary} />);
    expect(screen.getByText(item.quote).tagName).toBe("BLOCKQUOTE");
    expect(screen.getByText(/Suggested/)).toBeTruthy();
    expect(screen.getByText(/No owner/)).toBeTruthy();
    expect(screen.getByText(/Same CI job/)).toBeTruthy();
    expect(screen.getByText("Synthetic data")).toBeTruthy();
    expect(screen.getByText("1 of 2 reviewed")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull();
  });

  it("shows the new RAID ID after an approver confirms", async () => {
    viewer.approver = true;
    confirmRaid.mockResolvedValue({ ...item, review: "confirmed", raid_id: "K8S-R-002" });
    render(<ReviewQueue queue={queue} summary={summary} />);
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect((await screen.findByRole("status")).textContent).toContain("Confirmed as K8S-R-002");
    expect(screen.queryByText(item.quote)).toBeNull();
  });
});
