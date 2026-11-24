// Content-Security-Policy with a fresh nonce per request (#65; Next.js 16's CSP guide).
// Next.js puts the nonce on its own scripts, so a script injected into a page cannot run.
// CSP_MODE=report-only switches to Content-Security-Policy-Report-Only without a code
// change, if a page ever breaks in production.
import { NextResponse, type NextRequest } from "next/server";

const API_ORIGIN = new URL(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").origin;

export function buildCsp(nonce: string, isDev: boolean): string {
  return [
    "default-src 'self'",
    // 'strict-dynamic' lets scripts Next.js loads with the nonce load their own chunks.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    // React Flow, Recharts and components set inline style attributes.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    // The browser reads live updates (EventSource) and simulator results from the API.
    `connect-src 'self' ${API_ORIGIN}`,
    "object-src 'none'",
    "base-uri 'self'",
    // GitHub sign-in posts a form and is redirected to github.com; Chrome applies
    // form-action to that redirect.
    "form-action 'self' https://github.com",
    "frame-ancestors 'none'",
    "upgrade-insecure-requests",
  ].join("; ");
}

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = buildCsp(nonce, process.env.NODE_ENV === "development");
  const header =
    process.env.CSP_MODE === "report-only" ? "Content-Security-Policy-Report-Only" : "Content-Security-Policy";
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set(header, csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set(header, csp);
  return response;
}

export const config = {
  matcher: [
    // Pages only: not API routes, static files, images or link prefetches.
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
