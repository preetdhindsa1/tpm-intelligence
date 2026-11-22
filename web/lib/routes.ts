// URLs and project grouping for the multi-project shell (ADR-0014). Release names are
// only unique within a project (Kubernetes "v1.38", Kafka "4.3.0"), so every page URL
// carries the project: /projects/{project}/releases/{name}.
import type { Release } from "@/lib/api";

/** URL segment for a release's project ("kubernetes", "kafka"). */
export function projectSlug(r: Pick<Release, "project">): string {
  return r.project.toLowerCase();
}

/** Page URL for a release, optionally a section of it ("/dependencies"). */
export function releasePath(project: string, release: string, section = ""): string {
  return `/projects/${encodeURIComponent(project.toLowerCase())}/releases/${encodeURIComponent(release)}${section}`;
}

export type ProjectGroup = { slug: string; displayName: string; releases: Release[] };

/** Releases grouped by project, projects in first-seen order, releases oldest first. */
export function groupByProject(releases: Release[]): ProjectGroup[] {
  const groups = new Map<string, ProjectGroup>();
  for (const r of releases) {
    const slug = projectSlug(r);
    const g = groups.get(slug) ?? { slug, displayName: r.display_name || r.project, releases: [] };
    g.releases.push(r);
    groups.set(slug, g);
  }
  return [...groups.values()];
}

/** The release that matches a URL, or undefined (the page then returns 404). */
export function findRelease(releases: Release[], project: string, name: string): Release | undefined {
  const slug = decodeURIComponent(project).toLowerCase();
  const n = decodeURIComponent(name);
  return releases.find((r) => projectSlug(r) === slug && r.name === n);
}

/**
 * The release a project is working on now: the earliest one not yet shipped (release
 * day in the future or unknown), else the latest one. Dates are compared to `asOf`.
 */
export function currentRelease(releases: Release[], asOf: Date): Release | undefined {
  const open = releases.filter((r) => !r.release_at || new Date(r.release_at) > asOf);
  return open[0] ?? releases.at(-1);
}

/** Sections that exist in every release; a feature page may not, so switching drops it. */
const PORTABLE_SECTIONS = ["/dependencies", "/simulate", "/update", "/links"];

/** Where to go when the switcher picks another release: keep the section if portable. */
export function switchPath(pathname: string, project: string, release: string): string {
  const m = pathname.match(/^\/projects\/[^/]+\/releases\/[^/]+(\/[^/]+)?/);
  const section = m?.[1] && PORTABLE_SECTIONS.includes(m[1]) ? m[1] : "";
  return releasePath(project, release, section);
}

/** Next milestone after `asOf` (for the home cards), or null when the release has shipped. */
export function nextMilestone(r: Release, asOf: Date): { label: string; at: string } | null {
  const steps: [string, string | null][] = [
    ["Enhancements Freeze", r.enhancements_freeze_at],
    ["Code Freeze", r.code_freeze_at],
    ["Release", r.release_at],
  ];
  for (const [label, at] of steps) if (at && new Date(at) > asOf) return { label, at };
  return null;
}
