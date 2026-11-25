import { describe, expect, it } from "vitest";
import { DEMO_CHAPTERS, freezeStory, measuredStory, reviewStory } from "./front";
import { MEASURED } from "./measured";

describe("front page stories", () => {
  it("uses a freeze count only when the summary has one", () => {
    expect(freezeStory("Kubernetes", "v1.38", 33, "2026-11-25T00:00:00Z")?.title).toBe("33 removed at Code Freeze");
    expect(freezeStory("Kubernetes", "v1.38", 0, "2026-11-25T00:00:00Z")).toBeNull();
  });

  it("uses the lab's approving-review count and skips an empty release", () => {
    expect(reviewStory("This repo", 0, 43, "2026-11-24T00:00:00Z")?.title).toBe(
      "0 of 43 merged pull requests had an approving review",
    );
    expect(reviewStory("This repo", 0, 0, "2026-11-24T00:00:00Z")).toBeNull();
  });

  it("copies the Kafka linking result from the measured list", () => {
    const story = measuredStory(MEASURED, "kafka-linking");
    expect(story?.title).toBe("21 / 26");
    expect(story?.asOf).toBe("2026-11-23");
    expect(measuredStory(MEASURED, "unseen-test")).toBeNull();
  });

  it("lists five demo chapters and no video", () => {
    expect(DEMO_CHAPTERS).toHaveLength(5);
  });
});
