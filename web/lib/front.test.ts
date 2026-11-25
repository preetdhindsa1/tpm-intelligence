import { describe, expect, it } from "vitest";
import { DEMO_CHAPTERS, freezeStory, measuredStory } from "./front";
import { MEASURED } from "./measured";

describe("front page stories", () => {
  it("uses a freeze count only when the summary has one", () => {
    const story = freezeStory("Kubernetes", "v1.38", 33, 17, "2026-11-25T00:00:00Z");
    expect(story?.title).toBe("33 removed at Code Freeze");
    expect(story?.detail).toContain("17 were added back later.");
    expect(freezeStory("Kubernetes", "v1.38", 0, 0, "2026-11-25T00:00:00Z")).toBeNull();
    expect(freezeStory("Kubernetes", "v1.38", 33, 0, "2026-11-25T00:00:00Z")?.detail).not.toContain("added back");
  });

  it("copies the Kafka linking result from the measured list", () => {
    const story = measuredStory(MEASURED, "kafka-linking");
    expect(story?.title).toBe("21 / 26");
    expect(story?.asOf).toBe("2026-11-23");
    expect(measuredStory(MEASURED, "unseen-test")).toBeNull();
    expect(measuredStory(MEASURED, "fact-checker")?.title).toBe("43 / 43");
  });

  it("lists five demo chapters and no video", () => {
    expect(DEMO_CHAPTERS).toHaveLength(5);
  });
});
