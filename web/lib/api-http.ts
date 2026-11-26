// Shared HTTP for the RAID and readiness clients. Actions go through web/app/api/act,
// which adds the signed-in user's signature (ADR-0016). A 403 never shows a login.
import { serverApiUrl } from "@/lib/api";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const FIXED: Record<number, string> = {
  401: "Sign in to do this.",
  403: "Only an approver can change this. The page is read-only.",
  404: "Not found.",
  409: "This item was already rejected, so it cannot be changed.",
};

/** Clear text for an HTTP error. 401 and 403 never repeat the API's detail. */
export function messageFor(status: number, detail: unknown): string {
  if (status in FIXED) return FIXED[status];
  if (status === 422) {
    return textDetail(detail) ?? "That change was not accepted. A reason or note needs at least 3 characters.";
  }
  return textDetail(detail) ?? `The request failed (HTTP ${status}).`;
}

/** A string detail with no login in it. Validation-error arrays are ignored. */
function textDetail(detail: unknown): string | null {
  if (typeof detail !== "string" || !detail.trim()) return null;
  if (/@|\blogin\b/i.test(detail)) return null;
  return detail;
}

async function read<T>(res: Response): Promise<T> {
  if (res.ok) return (await res.json()) as T;
  const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
  throw new ApiError(res.status, messageFor(res.status, body.detail));
}

/** Server-side GET. Throws ApiError, including 404. */
export function serverGet<T>(path: string): Promise<T> {
  return fetch(`${serverApiUrl}${path}`, { cache: "no-store" }).then((res) => read<T>(res));
}

/** Browser GET through the signed same-origin route. */
export function browserGet<T>(path: string): Promise<T> {
  return fetch(`/api/act${path}`, { cache: "no-store" }).then((res) => read<T>(res));
}

/** Browser POST through the signed same-origin route. */
export function act<T>(path: string, body: unknown): Promise<T> {
  return fetch(`/api/act${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  }).then((res) => read<T>(res));
}
