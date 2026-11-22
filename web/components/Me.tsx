"use client";

// Who the browser is acting as, from the API through the signed route (ADR-0016). The
// API enforces permissions; this only decides which buttons to offer.
import Link from "next/link";
import { useEffect, useState } from "react";

export type Me = { login: string | null; signed_in: boolean; approver: boolean; mode: string };

export function useMe(): Me | null {
  const [me, setMe] = useState<Me | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch("/api/act/me", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((m: Me | null) => !cancelled && setMe(m))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  return me;
}

/** A line explaining why actions are unavailable, or nothing when the user may act. */
export function ApproverNote({ me, action }: { me: Me | null; action: string }) {
  if (!me || me.approver) return null;
  return (
    <p className="rounded bg-slate-50 px-3 py-2 text-sm text-slate-600">
      {me.signed_in ? (
        <>Signed in as {me.login}, who is not an approver, so you can read but not {action}.</>
      ) : (
        <>
          <Link href="/api/auth/signin" prefetch={false} className="font-medium text-indigo-700 hover:underline">
            Sign in with GitHub
          </Link>{" "}
          as an approver to {action}. Reading is open to everyone.
        </>
      )}
    </p>
  );
}
