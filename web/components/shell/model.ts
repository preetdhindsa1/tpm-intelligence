// Navigation targets and the lifecycle stage. Dates only. ADR-0024.
export type LastProgram = { project: string; release: string; displayName: string };
const KEY = "pi.lastProgram";

export function readLast(storage: { getItem(key: string): string | null }): LastProgram | null {
  try {
    const v = JSON.parse(storage.getItem(KEY) ?? "") as Partial<LastProgram>;
    if (!v.project || !v.release || !v.displayName) return null;
    return { project: v.project, release: v.release, displayName: v.displayName };
  } catch {
    return null;
  }
}

const LAST_EVENT = "pi-last-program";

export function writeLast(storage: { setItem(key: string, value: string): void }, value: LastProgram): void {
  storage.setItem(KEY, JSON.stringify(value));
  if (typeof window !== "undefined") window.dispatchEvent(new Event(LAST_EVENT));
}

let cachedRaw: string | null = null;
let cached: LastProgram | null = null;

/** Stable snapshot for useSyncExternalStore. Server render returns null. */
export function readLastSnapshot(): LastProgram | null {
  const raw = window.localStorage.getItem(KEY);
  if (raw === cachedRaw) return cached;
  cachedRaw = raw;
  cached = readLast(window.localStorage);
  return cached;
}

export function subscribeLast(onChange: () => void): () => void {
  window.addEventListener(LAST_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(LAST_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export type ReleaseDates = { cycle_start_at: string | null; code_freeze_at: string | null; release_at: string | null };

const STAGES = ["Plan", "Build", "Verify", "Launch", "Learn"] as const;
const LAUNCH_MS = 7 * 86_400_000;

/** Same boundaries as ADR-0025: cycle start, Code Freeze, release, release + 7 days. */
export function stageOf(r: ReleaseDates, asOf: Date): string {
  const at = (s: string | null) => (s ? new Date(s).getTime() : Number.NaN);
  const start = at(r.cycle_start_at);
  const freeze = at(r.code_freeze_at);
  const release = at(r.release_at);
  if (Number.isNaN(start) || Number.isNaN(freeze) || Number.isNaN(release)) return "Dates not known";
  const passed = [start, freeze, release, release + LAUNCH_MS].filter((b) => b <= asOf.getTime()).length;
  return STAGES[passed] ?? "Learn";
}

export type Dest = { id: string; href: string; label: string };

export function releaseFromPath(pathname: string): { project: string; release: string } | null {
  const m = pathname.match(/^\/projects\/([^/]+)\/releases\/([^/]+)/);
  if (!m) return null;
  return { project: decodeURIComponent(m[1]), release: decodeURIComponent(m[2]) };
}

function hrefFor(section: "" | "/simulate", path: string, last: LastProgram | null): string {
  const here = releaseFromPath(path) ?? (last ? { project: last.project, release: last.release } : null);
  if (!here) return "/portfolio";
  return `/projects/${encodeURIComponent(here.project)}/releases/${encodeURIComponent(here.release)}${section}`;
}

export function destinations(path: string, last: LastProgram | null): Dest[] {
  return [
    { id: "portfolio", href: "/portfolio", label: "Portfolio" },
    { id: "cockpit", href: hrefFor("", path, last), label: "Live Cockpit" },
    { id: "studio", href: hrefFor("/simulate", path, last), label: "Decision Studio" },
    { id: "pdlc", href: "/pdlc", label: "AI-native PDLC" },
    { id: "connect", href: "/connect", label: "Connect your tools" },
  ];
}

export function currentId(path: string): string | null {
  if (path.startsWith("/portfolio")) return "portfolio";
  if (path.startsWith("/pdlc") || path.startsWith("/lab")) return "pdlc";
  if (path.startsWith("/connect")) return "connect";
  if (path.includes("/simulate")) return "studio";
  if (path.startsWith("/projects/")) return "cockpit";
  return null;
}

/** Live Cockpit sections. Decision Studio is a top-level screen, so it is not a section. */
export const COCKPIT_SECTIONS: { suffix: string; label: string }[] = [
  { suffix: "", label: "Overview" },
  { suffix: "/dependencies", label: "Dependencies" },
  { suffix: "/update", label: "Executive update" },
  { suffix: "/links", label: "Link review" },
  { suffix: "/raid", label: "RAID" },
  { suffix: "/readiness", label: "Readiness" },
  { suffix: "/retro", label: "Retro" },
];

/** The section a release path is on; feature pages belong to Overview. Null on Decision Studio. */
export function cockpitSection(path: string): string | null {
  const m = path.match(/^\/projects\/[^/]+\/releases\/[^/]+(\/[^/]*)?/);
  if (!m) return null;
  const rest = m[1] ?? "";
  if (rest === "/simulate") return null;
  return COCKPIT_SECTIONS.find((s) => s.suffix !== "" && s.suffix === rest)?.suffix ?? "";
}

export function commandItems(path: string, last: LastProgram | null): { href: string; label: string }[] {
  const top = destinations(path, last).map(({ href, label }) => ({ href, label }));
  const here = releaseFromPath(path);
  if (!here) return top;
  const base = `/projects/${encodeURIComponent(here.project)}/releases/${encodeURIComponent(here.release)}`;
  return [...top, ...COCKPIT_SECTIONS.map(({ suffix, label }) => ({ href: `${base}${suffix}`, label: `Live Cockpit · ${label}` }))];
}
