// Header sign-in state (server component; ADR-0016). Whether someone may act is decided
// by the API, so this only shows who is signed in.
//
// Signed-out visitors see no sign-in button here: reading needs no account, and the pages
// where an approver acts (Update, Links) offer sign-in themselves. A login button on every
// page of a new run.app address got the site flagged by Chrome's phishing check
// (2026-11-23), so the front page should read as a dashboard, not a login page.
import Link from "next/link";
import { getServerSession } from "next-auth";
import { authOptions, devLoginEnabled, githubEnabled, type TpmSession } from "@/lib/auth";

export async function AuthStatus() {
  if (!githubEnabled() && !devLoginEnabled()) return null;
  const session = (await getServerSession(authOptions())) as TpmSession;
  if (!session?.login) return null;
  return (
    <span className="flex items-center gap-3 text-sm text-slate-600">
      <span>
        Signed in as <strong className="font-medium text-slate-800">{session.login}</strong>
      </span>
      <Link href="/api/auth/signout" prefetch={false} className="text-action hover:underline">
        Sign out
      </Link>
    </span>
  );
}
