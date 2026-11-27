// Signs actions the web server forwards to the API on behalf of a signed-in user
// (ADR-0016). Must match api/auth.py `signature` byte for byte.
import { createHash, createHmac } from "node:crypto";

export function signature(secret: string, user: string, ts: string, method: string, path: string, body: string, tenant?: string): string {
  const digest = createHash("sha256").update(body, "utf8").digest("hex");
  const lines = [user, ts, method.toUpperCase(), path, digest];
  if (tenant) lines.push(tenant);
  return createHmac("sha256", secret).update(lines.join("\n"), "utf8").digest("hex");
}

/** Headers that tell the API who is acting; empty when nobody is signed in. */
export function signedHeaders(
  secret: string | undefined,
  login: string | null | undefined,
  method: string,
  path: string,
  body: string,
  now: number = Date.now(),
  tenant?: string,
): Record<string, string> {
  if (!secret || !login) return {};
  const ts = String(Math.floor(now / 1000));
  const headers: Record<string, string> = {
    "x-tpm-user": login,
    "x-tpm-time": ts,
    "x-tpm-signature": signature(secret, login, ts, method, path, body, tenant),
  };
  if (tenant) {
    headers["x-tpm-signature-version"] = "2";
    headers["x-tpm-tenant"] = tenant;
  }
  return headers;
}

/** API path for a forwarded request; refuses anything that could escape the API root. */
export function forwardPath(segments: string[], search: string): string | null {
  if (!segments.length || segments.some((s) => s === "" || s === "." || s === ".." || s.includes("/"))) return null;
  return `/${segments.map(encodeURIComponent).join("/")}${search}`;
}
