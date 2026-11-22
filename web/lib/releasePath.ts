/** Parse `/releases/{name}/...` from a pathname. */
export function releaseFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/releases\/([^/]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export function releaseHref(release: string | null, section: "dashboard" | "dependencies" | "simulator" | "reports"): string {
  if (!release) {
    return section === "dashboard" ? "/" : `/#${section}`;
  }
  if (section === "dashboard") return `/releases/${release}`;
  return `/releases/${release}/${section}`;
}
