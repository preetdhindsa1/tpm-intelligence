// Turning a failed API call into page text. lib/api.ts throws "<path>: HTTP <status>".

/** The failure text to show, or the fallback when the error carries none. */
export function errorDetail(e: unknown, fallback: string): string {
  return e instanceof Error && e.message ? e.message : fallback;
}

/** True when the API said the thing does not exist, so the page should 404 rather than show an error. */
export function isNotFound(detail: string): boolean {
  return /: HTTP 404$/.test(detail);
}
