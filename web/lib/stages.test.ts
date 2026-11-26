import { describe, expect, it } from "vitest";
import { STAGES } from "./front";
import { NOT_STARTED, frontStages, launchLearn, stageCaption } from "./stages";

const PATHS = {
  launch: "/projects/kubernetes/releases/v1.38/readiness",
  learn: "/projects/kubernetes/releases/v1.38/retro",
};

describe("Launch and Learn", () => {
  it("links a stage only when that module is live", () => {
    const modules = launchLearn(
      [
        { module: "readiness", status: "live" },
        { module: "retro", status: "planned" },
      ],
      PATHS,
    );
    expect(modules.launch).toEqual({ live: true, href: PATHS.launch });
    expect(modules.learn).toEqual({ live: false, href: null });

    const cards = frontStages(STAGES, modules);
    expect(cards.map((s) => s.stage)).toEqual(["Plan", "Build", "Verify", "Launch", "Learn"]);
    expect(cards.find((s) => s.stage === "Launch")?.tags.map((t) => t.text)).toEqual(["Live"]);
    expect(cards.find((s) => s.stage === "Launch")?.href).toBe(PATHS.launch);
    expect(cards.find((s) => s.stage === "Learn")?.tags.map((t) => t.text)).toEqual([NOT_STARTED]);
    expect(cards.find((s) => s.stage === "Learn")?.href).toBeNull();
    expect(cards.find((s) => s.stage === "Plan")?.href).toBeNull();
    expect(stageCaption("launch", "upcoming", modules)).toEqual({ text: "Live", href: PATHS.launch });
    expect(stageCaption("learn", "upcoming", modules)).toEqual({ text: NOT_STARTED, href: null });
    expect(stageCaption("verify", "current", modules)).toEqual({ text: "current", href: null });
  });

  it("shows not started when the API returns no module data", () => {
    const modules = launchLearn(undefined, PATHS);
    expect(modules.launch.live).toBe(false);
    expect(modules.learn.href).toBeNull();
    const cards = frontStages(STAGES, modules);
    expect(cards.filter((s) => s.stage === "Launch" || s.stage === "Learn").flatMap((s) => s.tags.map((t) => t.text))).toEqual([
      NOT_STARTED,
      NOT_STARTED,
    ]);
    expect(cards.every((s) => s.href === null)).toBe(true);
  });
});
