import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SaidVsShowed } from "@/lib/api-readiness";
import { SaidTimeline } from "./SaidVsShowed";

afterEach(cleanup);

const data: SaidVsShowed = {
  project: "kubernetes",
  release: "v1.37",
  synthetic: false,
  rows: [
    {
      date: "2026-11-10T12:00:00Z",
      said: [
        {
          item_id: 1,
          raid_id: null,
          type: "risk",
          title: "CI flakes",
          review: "suggested",
          quote: "the node e2e job flakes",
        },
      ],
      showed: [
        { name: "replay_day", value: "2026-11-10" },
        { name: "features_at_risk", value: 3 },
        { name: "critical_flags", value: null },
      ],
    },
  ],
};

describe("SaidTimeline", () => {
  it("shows the meeting next to that day's counts and does not judge the risk", () => {
    render(<SaidTimeline data={data} />);
    expect(screen.getByText("the node e2e job flakes").textContent).toBe("the node e2e job flakes");
    expect(screen.getByText("Suggested").textContent).toBe("Suggested");
    expect(screen.getByText("Features at risk: 3").textContent).toBe("Features at risk: 3");
    expect(screen.getByText("Critical flags: not measured").textContent).toBe("Critical flags: not measured");
    expect(screen.queryByText("Raised before the platform")).toBeNull();
    expect(screen.queryByText("Raised after the platform")).toBeNull();
    expect(screen.queryByText("The platform never showed it")).toBeNull();
  });
});
