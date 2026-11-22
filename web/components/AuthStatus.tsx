// Header sign-in state (server component; ADR-0016). Whether someone may act is decided
// by the API, so this only shows who is signed in.
import Link from "next/link";
import { getServerSession } from "next-auth";
import { authOptions, devLoginEnabled, githubEnabled, type TpmSession } from "@/lib/auth";

export async function AuthStatus() {
  if (!githubEnabled() && !devLoginEnabled()) {
    return <span className="text-xs text-slate-400">Read-only (sign-in not configured)</span>;
  }
  const session = (await getServerSession(authOptions())) as TpmSession;
  if (!session?.login) {
    return (
      <Link href="/api/auth/signin" prefetch={false} className="rounded-md border px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50">
        Sign in with GitHub
      </Link>
    );
  }
  return (
    <span className="flex items-center gap-3 text-sm text-slate-600">
      <span>
        Signed in as <strong className="font-medium text-slate-800">{session.login}</strong>
      </span>
      <Link href="/api/auth/signout" prefetch={false} className="text-indigo-700 hover:underline">
        Sign out
      </Link>
    </span>
  );
}
