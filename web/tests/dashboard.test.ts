import { describe, expect, it } from "vitest";
import type { ExecUpdate, Summary } from "../lib/api";
import { briefToShow, outcomeRows, topBadge } from "../lib/dashboard";

describe("outcomes and badges", () => {
  it("orders outcome bars and names their features", () => {
    const s = {
      outcomes: { removed_at_freeze: 2, landed: 5 },
      features: [{ key: "k", number: 1979, title: "COSI", outcome: "removed_at_freeze", sigs: [] }],
    } as unknown as Summary;
    const rows = outcomeRows(s);
    expect(rows.map((r) => r.outcome)).toEqual(["landed", "removed_at_freeze"]);
    expect(rows[1].features).toEqual(["#1979 COSI"]);
    expect(rows[1].color).toBe("#d03b3b");
  });
  it("picks the most important flag", () => {
    expect(topBadge(["ci_failing", "main_pr_not_merged"])).toBe("Main PR missed freeze");
    expect(topBadge([])).toBeNull();
  });
});

describe("briefToShow", () => {
  const u = (id: number, status: ExecUpdate["status"], created_at: string) => ({ id, status, created_at }) as ExecUpdate;
  it("prefers the newest approved update, else the newest draft", () => {
    expect(briefToShow([u(1, "approved", "2026-11-20"), u(2, "draft", "2026-11-22")])?.id).toBe(1);
    expect(briefToShow([u(1, "draft", "2026-11-20"), u(2, "draft", "2026-11-22"), u(3, "rejected", "2026-11-23")])?.id).toBe(2);
    expect(briefToShow([u(3, "rejected", "2026-11-23")])).toBeNull();
  });
});
