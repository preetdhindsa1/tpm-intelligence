"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { publicApiUrl } from "@/lib/api";

/** Subscribes to the API's SSE stream and re-renders the page on each "update". */
export function LiveRefresh({ release }: { release: string }) {
  const router = useRouter();
  const [state, setState] = useState<"connecting" | "live" | "offline">("connecting");
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const seenVersion = useRef<number | null>(null);

  useEffect(() => {
    const source = new EventSource(`${publicApiUrl}/releases/${release}/stream`);
    source.addEventListener("ready", (e) => {
      setState("live");
      // The server ends each stream after a while and the browser reconnects, possibly to
      // a newer API revision. Refresh if anything changed while we were away.
      const { version } = JSON.parse((e as MessageEvent).data) as { version: number };
      if (seenVersion.current !== null && seenVersion.current !== version) router.refresh();
      seenVersion.current = version;
    });
    source.addEventListener("update", (e) => {
      const data = JSON.parse((e as MessageEvent).data) as { as_of: string; version: number };
      seenVersion.current = data.version;
      setUpdatedAt(data.as_of);
      router.refresh();
    });
    // A planned reconnect is not an outage: show "Connecting", not "offline".
    source.onerror = () =>
      setState(source.readyState === EventSource.CONNECTING ? "connecting" : "offline");
    return () => source.close();
  }, [release, router]);

  const dot = state === "live" ? "bg-emerald-500" : state === "offline" ? "bg-rose-500" : "bg-amber-400";
  return (
    <span className="inline-flex items-center gap-2 text-xs text-slate-500" aria-live="polite">
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      {state === "live" ? "Live" : state === "offline" ? "Live updates offline" : "Connecting"}
      {updatedAt ? ` · updated ${updatedAt.slice(11, 19)} UTC` : ""}
    </span>
  );
}
