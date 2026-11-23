import { describe, expect, it } from "vitest";
import { SELF_PROJECT, teamState } from "@/lib/teams";

describe("front-page team cards", () => {
  it("marks a card live only when the API serves that display name", () => {
    expect(teamState(SELF_PROJECT, new Set([SELF_PROJECT]))).toBe("Live");
    expect(teamState(SELF_PROJECT, new Set(["Kubernetes"]))).toBe("Built · waiting for the first issues");
    expect(teamState("Your team", new Set())).toBe("Plug in");
  });
});
