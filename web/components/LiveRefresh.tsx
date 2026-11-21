"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { publicApiUrl } from "@/lib/api";

/** Subscribes to the API's SSE stream and re-renders the page on each "update". */
export function LiveRefresh({ release }: { release: string }) {
  const router = useRouter();
  const [state, setState] = useState<"connecting" | "live" | "offline">("connecting");
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  useEffect(() => {
    const source = new EventSource(`${publicApiUrl}/releases/${release}/stream`);
    source.addEventListener("ready", () => setState("live"));
    source.addEventListener("update", (e) => {
      const data = JSON.parse((e as MessageEvent).data) as { as_of: string };
      setUpdatedAt(data.as_of);
      router.refresh();
    });
    source.onerror = () => setState("offline");
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
