import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Patterns, Retro } from "@/lib/api-readiness";
import { RetroView } from "./RetroView";

afterEach(cleanup);

const retro: Retro = {
  project: "kubernetes", release: "v1.37", label: "Kubernetes v1.37, public retro", as_of: "2026-11-25T21:00:00Z", synthetic: false,
  sources: [], totals: { slips: 0, warned: 0, average_lead_time_days: null, median_lead_time_days: null }, slips: [],
};

const patterns: Patterns = {
  project: "kubernetes", synthetic: false, min_group: 10, suppressed_groups: 4, patterns: [],
};

describe("RetroView", () => {
  it("shows the public v1.37 label and how many groups are too small", () => {
    render(<RetroView retro={retro} patterns={patterns} />);
    expect(screen.getByRole("heading", { name: "Kubernetes v1.37, public retro" }).textContent).toBe("Kubernetes v1.37, public retro");
    expect(screen.getByText("4 groups too small to show").textContent).toBe("4 groups too small to show");
    expect(screen.getByText("No slips.").textContent).toBe("No slips.");
  });
});