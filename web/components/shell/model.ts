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

export type ReleaseDates = { enhancements_freeze_at: string | null; code_freeze_at: string | null; release_at: string | null };

/** Compared to the release as_of, in UTC. "Dates not known" when nothing is dated. */
export function stageOf(r: ReleaseDates, asOf: Date): string {
  const t = asOf.getTime();
  const at = (s: string | null) => (s ? new Date(s).getTime() : null);
  const rel = at(r.release_at);
  const cf = at(r.code_freeze_at);
  const ef = at(r.enhancements_freeze_at);
  if (rel !== null && t >= rel) {
    const day = (n: number) => new Date(n).toISOString().slice(0, 10);
    return day(t) === day(rel) ? "Launch" : "Learn";
  }
  if (cf !== null && t >= cf) return "Freeze";
  if (ef !== null && t >= ef) return "Build";
  if (rel !== null || cf !== null || ef !== null) return "Plan";
  return "Dates not known";
}

export type Dest = { id: string; href: string; label: string };

export function releaseFromPath(pathname: string): { project: string; release: string } | null {
  const m = pathname.match(/^\/projects\/([^/]+)\/releases\/([^/]+)/);
  if (!m) return null;
  return { project: decodeURIComponent(m[1]), release: decodeURIComponent(m[2]) };
}

function hrefFor(section: "" | "/simulate", path: string, last: LastProgram | null): string {
  const here = releaseFromPath(path) ?? (last ? { project: last.project, release: last.release } : null);
  if (!here) return "/releases";
  return `/projects/${encodeURIComponent(here.project)}/releases/${encodeURIComponent(here.release)}${section}`;
}

export function destinations(path: string, last: LastProgram | null): Dest[] {
  return [
    { id: "portfolio", href: "/portfolio", label: "Portfolio" },
    { id: "cockpit", href: hrefFor("", path, last), label: "Live Cockpit" },
    { id: "studio", href: hrefFor("/simulate", path, last), label: "Decision Studio" },
    { id: "pdlc", href: "/lab", label: "AI-native PDLC" },
    { id: "connect", href: "/connect", label: "Connect your tools" },
  ];
}

export function currentId(path: string): string | null {
  if (path.startsWith("/portfolio")) return "portfolio";
  if (path.startsWith("/lab")) return "pdlc";
  if (path.startsWith("/connect")) return "connect";
  if (path.includes("/simulate")) return "studio";
  if (path.startsWith("/projects/")) return "cockpit";
  return null;
}

const SECTIONS: [string, string][] = [["", "Dashboard"], ["/dependencies", "Dependencies"], ["/simulate", "Simulations"], ["/update", "Reports"], ["/links", "Link review"]];

export function commandItems(path: string, last: LastProgram | null): { href: string; label: string }[] {
  const top = destinations(path, last).map(({ href, label }) => ({ href, label }));
  const here = releaseFromPath(path);
  if (!here) return top;
  const base = `/projects/${encodeURIComponent(here.project)}/releases/${encodeURIComponent(here.release)}`;
  return [...top, ...SECTIONS.map(([suffix, label]) => ({ href: `${base}${suffix}`, label }))];
}
