import { describe, expect, it } from "vitest";
import type { Release } from "@/lib/api";
import { currentRelease, findRelease, groupByProject, nextMilestone, releasePath, switchPath } from "@/lib/routes";

const rel = (project: string, name: string, release_at: string | null, extra: Partial<Release> = {}): Release => ({
  key: `${project}:${name}`,
  name,
  project,
  display_name: project === "kubernetes" ? "Kubernetes" : "Apache Kafka",
  cycle_start_at: null,
  enhancements_freeze_at: null,
  code_freeze_at: null,
  release_at,
  features_in_release: 0,
  features_ever_in_release: 0,
  as_of: "2026-11-22T00:00:00Z",
  ...extra,
});

const K37 = rel("kubernetes", "v1.37", "2026-08-26T00:00:00Z");
const K38 = rel("kubernetes", "v1.38", "2026-12-16T00:00:00Z", {
  enhancements_freeze_at: "2026-09-30T12:00:00Z",
  code_freeze_at: "2026-11-17T12:00:00Z",
});
const KAFKA = rel("KAFKA", "4.3.0", null);
const NOW = new Date("2026-11-22T00:00:00Z");

describe("release routes", () => {
  it("puts the project in every release URL, lower-cased", () => {
    expect(releasePath("kubernetes", "v1.38")).toBe("/projects/kubernetes/releases/v1.38");
    expect(releasePath("KAFKA", "4.3.0", "/simulate")).toBe("/projects/kafka/releases/4.3.0/simulate");
  });

  it("finds a release only within its own project", () => {
    const all = [K37, K38, KAFKA];
    expect(findRelease(all, "kubernetes", "v1.38")).toBe(K38);
    expect(findRelease(all, "kafka", "4.3.0")).toBe(KAFKA);
    expect(findRelease(all, "kafka", "v1.38")).toBeUndefined();
  });

  it("groups by project, keeping release order", () => {
    const g = groupByProject([K37, KAFKA, K38]);
    expect(g.map((x) => x.slug)).toEqual(["kubernetes", "kafka"]);
    expect(g[0].releases.map((r) => r.name)).toEqual(["v1.37", "v1.38"]);
    expect(g[1].displayName).toBe("Apache Kafka");
  });

  it("picks the earliest unshipped release as current, else the latest", () => {
    expect(currentRelease([K37, K38], NOW)).toBe(K38);
    expect(currentRelease([K37], NOW)).toBe(K37);
    expect(currentRelease([K37, K38], new Date("2027-01-01T00:00:00Z"))).toBe(K38);
  });

  it("keeps portable sections when switching release, drops feature pages", () => {
    expect(switchPath("/projects/kubernetes/releases/v1.38/dependencies", "kubernetes", "v1.37")).toBe(
      "/projects/kubernetes/releases/v1.37/dependencies",
    );
    expect(switchPath("/projects/kubernetes/releases/v1.38/features/6395", "kubernetes", "v1.37")).toBe(
      "/projects/kubernetes/releases/v1.37",
    );
    expect(switchPath("/projects/kubernetes/releases/v1.38", "kubernetes", "v1.37")).toBe("/projects/kubernetes/releases/v1.37");
  });

  it("names the next milestone, or none after release day", () => {
    expect(nextMilestone(K38, NOW)).toEqual({ label: "Release", at: "2026-12-16T00:00:00Z" });
    expect(nextMilestone(K38, new Date("2026-10-01T00:00:00Z"))?.label).toBe("Code Freeze");
    expect(nextMilestone(K37, NOW)).toBeNull();
  });
});
