// Signed reads of the tenant routes. The browser never sees the signing secret.
import { getServerSession } from "next-auth";
import { authOptions, type TpmSession } from "@/lib/auth";
import { serverApiUrl } from "@/lib/api";
import type { OrgList } from "@/lib/org";
import { signedHeaders } from "@/lib/sign";

export type Loaded<T> = { ok: true; data: T } | { ok: false; detail: string };

async function signedGet<T>(path: string, login: string, tenant?: string): Promise<Loaded<T>> {
  const res = await fetch(`${serverApiUrl}${path}`, {
    headers: { ...signedHeaders(process.env.TPM_ACTION_SECRET, login, "GET", path, "", Date.now(), tenant) },
    cache: "no-store",
  });
  const text = await res.text();
  if (!res.ok) {
    let detail = `The request failed (HTTP ${res.status}).`;
    try {
      const body = JSON.parse(text) as { detail?: unknown };
      if (typeof body.detail === "string" && body.detail.trim()) detail = body.detail;
    } catch {
      /* the status line is enough */
    }
    return { ok: false, detail };
  }
  return { ok: true, data: JSON.parse(text) as T };
}

export async function loadOrgList(): Promise<{ login: string | null; list: Loaded<OrgList> | null }> {
  const session = (await getServerSession(authOptions())) as TpmSession;
  const login = session?.login ?? null;
  if (!login) return { login: null, list: null };
  if (!process.env.TPM_ACTION_SECRET) return { login, list: { ok: false, detail: "Sign-in is not configured on this server." } };
  return { login, list: await signedGet<OrgList>("/me/tenants", login) };
}

export function loadTenant<T>(login: string, path: string, tenant: string): Promise<Loaded<T>> {
  return signedGet<T>(path, login, tenant === "demo" ? undefined : tenant);
}
