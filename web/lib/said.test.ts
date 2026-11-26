import { describe, expect, it } from "vitest";
import type { SaidItem, SaidRow } from "./api-readiness";
import { riskWhen } from "./said";

const risk: SaidItem = { item_id: 1, raid_id: null, type: "risk", title: "CI flakes", review: "suggested", quote: "the node e2e job flakes" };

function row(date: string, showed: SaidRow["showed"], said: SaidItem[] = [risk]): SaidRow {
  return { date, said, showed };
}

describe("risk timing", () => {
  it("marks a risk raised before the first replay day", () => {
    const early = row("2026-11-01T12:00:00Z", []);
    const later = row("2026-11-10T12:00:00Z", [{ name: "replay_day", value: "2026-11-10" }, { name: "features_at_risk", value: 3 }]);
    expect(riskWhen([early, later], early, risk)).toBe("before");
  });

  it("marks a risk raised after the platform had already shown a warning", () => {
    const first = row("2026-11-10T12:00:00Z", [{ name: "replay_day", value: "2026-11-10" }, { name: "critical_flags", value: 1 }], []);
    const later = row("2026-11-17T12:00:00Z", [{ name: "replay_day", value: "2026-11-17" }, { name: "features_at_risk", value: 2 }]);
    expect(riskWhen([first, later], later, risk)).toBe("after");
  });

  it("marks a risk the platform never showed", () => {
    const meeting = row("2026-11-10T12:00:00Z", [{ name: "replay_day", value: "2026-11-10" }, { name: "features_at_risk", value: 0 }, { name: "critical_flags", value: 0 }]);
    expect(riskWhen([meeting], meeting, risk)).toBe("never");
  });
});
