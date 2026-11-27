import { describe, expect, it } from "vitest";
import { STAGES } from "./front";
import { LIVE_UNVALIDATED, NO_DATA, frontStages, launchLearn, stageCaption } from "./stages";

const PATHS = {
  launch: "/projects/kubernetes/releases/v1.38/readiness",
  learn: "/projects/kubernetes/releases/v1.38/retro",
};

const LIVE = [
  { module: "readiness", status: "live", validated: false },
  { module: "retro", status: "live", validated: null },
];

describe("Launch and Learn", () => {
  it("labels an unvalidated readiness and does not link Learn without has_retro", () => {
    const modules = launchLearn(LIVE, PATHS);
    expect(modules.launch).toEqual({ live: true, href: PATHS.launch, label: LIVE_UNVALIDATED, tone: "warn" });
    expect(modules.learn).toEqual({ live: false, href: null, label: NO_DATA, tone: "planned" });

    const cards = frontStages(STAGES, modules);
    const launch = cards.find((s) => s.stage === "Launch");
    const learn = cards.find((s) => s.stage === "Learn");
    expect(launch?.tags.map((t) => t.text)).toEqual([LIVE_UNVALIDATED]);
    expect(launch?.tags[0]?.tone).toBe("warn");
    expect(launch?.href).toBe(PATHS.launch);
    expect(launch?.body).toContain("not validated");
    expect(learn?.tags.map((t) => t.text)).toEqual([NO_DATA]);
    expect(learn?.href).toBeNull();
    expect(stageCaption("launch", "upcoming", modules)).toEqual({ text: LIVE_UNVALIDATED, href: PATHS.launch });
    expect(stageCaption("learn", "upcoming", modules)).toEqual({ text: NO_DATA, href: null });
    expect(stageCaption("verify", "current", modules)).toEqual({ text: "current", href: null });
    const unknown = launchLearn([{ module: "readiness", status: "live", validated: null }], PATHS);
    expect(unknown.launch.label).toBe(LIVE_UNVALIDATED);
    expect(unknown.learn.href).toBeNull();
  });

  it("says Live only when readiness is validated, and links Learn only when has_retro is true", () => {
    const validated = launchLearn([{ module: "readiness", status: "live", validated: true }], PATHS, true);
    expect(validated.launch.label).toBe("Live");
    expect(validated.launch.tone).toBe("live");
    expect(validated.learn).toEqual({ live: true, href: PATHS.learn, label: "Live", tone: "live" });
    expect(frontStages(STAGES, validated).find((s) => s.stage === "Learn")?.href).toBe(PATHS.learn);
  });

  it("shows no data yet when the API returns no module data", () => {
    const modules = launchLearn(undefined, PATHS);
    expect(modules.launch.live).toBe(false);
    expect(modules.learn.href).toBeNull();
    const cards = frontStages(STAGES, modules);
    expect(cards.filter((s) => s.stage === "Launch" || s.stage === "Learn").flatMap((s) => s.tags.map((t) => t.text))).toEqual([
      NO_DATA,
      NO_DATA,
    ]);
    expect(cards.every((s) => s.href === null)).toBe(true);
  });
});
