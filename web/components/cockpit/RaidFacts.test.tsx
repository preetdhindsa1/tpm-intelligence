import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { RaidSummary } from "@/lib/api-raid";
import { NO_MEETING_NOTES } from "@/lib/raid-facts";
import { RaidFacts } from "./RaidFacts";

const summary: RaidSummary = {
  project: "kubernetes", release: "v1.38", as_of: "2026-11-25T21:00:00Z", synthetic: false,
  by_type: [{ type: "risk", suggested: 0, open: 2, in_progress: 0, closed: 0, superseded: 0, rejected: 0 }],
  risks_without_owner: 1, waiting_for_review: 3, sources: 1,
};

afterEach(cleanup);

describe("RAID cockpit strip", () => {
  it("links the counts when notes are connected", () => {
    render(<RaidFacts summary={summary} href="/projects/kubernetes/releases/v1.38/raid" />);
    expect(screen.getByRole("link", { name: "2 Open risks" }).getAttribute("href")).toBe("/projects/kubernetes/releases/v1.38/raid");
    expect(screen.getByRole("link", { name: "1 Risks without an owner" }).textContent).toBe("1 Risks without an owner");
    expect(screen.queryByText(NO_MEETING_NOTES)).toBeNull();
  });

  it("says nothing is connected instead of showing zeros", () => {
    render(<RaidFacts summary={{ ...summary, sources: 0, risks_without_owner: 0, waiting_for_review: 0 }} href="/raid" />);
    expect(screen.getByText(NO_MEETING_NOTES).textContent).toBe(NO_MEETING_NOTES);
    expect(screen.queryByRole("link")).toBeNull();
  });
});
