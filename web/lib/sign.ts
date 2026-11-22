// Signs actions the web server forwards to the API on behalf of a signed-in user
// (ADR-0016). Must match api/auth.py `signature` byte for byte.
import { createHash, createHmac } from "node:crypto";

export function signature(secret: string, user: string, ts: string, method: string, path: string, body: string): string {
  const digest = createHash("sha256").update(body, "utf8").digest("hex");
  const message = [user, ts, method.toUpperCase(), path, digest].join("\n");
  return createHmac("sha256", secret).update(message, "utf8").digest("hex");
}

/** Headers that tell the API who is acting; empty when nobody is signed in. */
export function signedHeaders(
  secret: string | undefined,
  login: string | null | undefined,
  method: string,
  path: string,
  body: string,
  now: number = Date.now(),
): Record<string, string> {
  if (!secret || !login) return {};
  const ts = String(Math.floor(now / 1000));
  return { "x-tpm-user": login, "x-tpm-time": ts, "x-tpm-signature": signature(secret, login, ts, method, path, body) };
}

/** API path for a forwarded request; refuses anything that could escape the API root. */
export function forwardPath(segments: string[], search: string): string | null {
  if (!segments.length || segments.some((s) => s === "" || s === "." || s === ".." || s.includes("/"))) return null;
  return `/${segments.map(encodeURIComponent).join("/")}${search}`;
}
