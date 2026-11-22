// Same-origin route for everything the browser asks of the API (ADR-0016). It adds the
// signed-in user's signature; the API decides whether they may act. No secret ever
// reaches the browser.
import { getServerSession } from "next-auth";
import { authOptions, type TpmSession } from "@/lib/auth";
import { forwardPath, signedHeaders } from "@/lib/sign";

export const dynamic = "force-dynamic";

const API = process.env.API_URL ?? "http://localhost:8000";

async function forward(req: Request, ctx: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path: segments } = await ctx.params;
  const path = forwardPath(segments, new URL(req.url).search);
  if (!path) return Response.json({ detail: "bad path" }, { status: 400 });
  const body = req.method === "GET" ? "" : await req.text();
  const session = (await getServerSession(authOptions())) as TpmSession;
  const res = await fetch(`${API}${path}`, {
    method: req.method,
    headers: {
      "content-type": "application/json",
      ...signedHeaders(process.env.TPM_ACTION_SECRET, session?.login, req.method, path, body),
    },
    body: req.method === "GET" ? undefined : body,
    cache: "no-store",
  });
  return new Response(await res.text(), { status: res.status, headers: { "content-type": res.headers.get("content-type") ?? "application/json" } });
}

export { forward as GET, forward as POST, forward as PATCH };
