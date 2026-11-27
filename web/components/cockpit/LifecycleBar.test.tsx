import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { LIVE_UNVALIDATED, NO_DATA, type LaunchLearn } from "@/lib/stages";
import { LifecycleBar } from "./LifecycleBar";

const steps = [
  { name: "Plan", note: "Cycle start", fill: 1, here: false },
  { name: "Launch", note: "Release 16 Dec", fill: 0, here: false },
  { name: "Learn", note: "Retro after release", fill: 0, here: false },
];

const live: LaunchLearn = {
  launch: { live: true, href: "/projects/kubernetes/releases/v1.38/readiness", label: LIVE_UNVALIDATED, tone: "warn" },
  learn: { live: false, href: null, label: NO_DATA, tone: "planned" },
};

afterEach(cleanup);

describe("LifecycleBar Launch and Learn", () => {
  it("links a live stage and marks the other not started", () => {
    const view = render(<LifecycleBar steps={steps} modules={live} />);
    const launch = view.getByRole("link", { name: "Launch" });
    expect(launch.getAttribute("href")).toBe("/projects/kubernetes/releases/v1.38/readiness");
    expect(view.getByText(LIVE_UNVALIDATED)).toBeTruthy();
    expect(view.getByText(NO_DATA)).toBeTruthy();
    expect(view.queryByRole("link", { name: "Learn" })).toBeNull();
  });

  it("marks both not started when the API has no module data", () => {
    const none: LaunchLearn = {
      launch: { live: false, href: null, label: NO_DATA, tone: "planned" },
      learn: { live: false, href: null, label: NO_DATA, tone: "planned" },
    };
    const view = render(<LifecycleBar steps={steps} modules={none} />);
    expect(view.container.querySelector("a")).toBeNull();
    expect(view.getAllByText(NO_DATA)).toHaveLength(2);
  });
});
