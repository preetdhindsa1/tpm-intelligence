"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApproverNote, useMe } from "@/components/Me";
import { postDecision, type Decision } from "@/lib/api-readiness";
import { decisionLabel, noteError } from "@/lib/readiness";

const CHOICES: Decision[] = ["go", "no_go", "defer"];

/** Go, no go or defer. Only an approver sees the form. The note is required. */
export function DecisionForm({ release }: { release: string }) {
  const me = useMe();
  const router = useRouter();
  const [decision, setDecision] = useState<Decision>("defer");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!me?.approver) return <ApproverNote me={me} action="record a go, no go or defer" />;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const problem = noteError(note);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await postDecision(release, decision, note.trim());
      setNote("");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The decision was not saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5">
      <h2 className="font-heading text-lg font-semibold">Record a decision</h2>
      <div className="flex flex-wrap gap-2">
        {CHOICES.map((choice) => (
          <label key={choice} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm">
            <input type="radio" name="decision" checked={decision === choice} onChange={() => setDecision(choice)} />
            {decisionLabel(choice)}
          </label>
        ))}
      </div>
      <label className="block text-sm text-slate-600">
        Note
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900" />
      </label>
      {error && <p className="text-sm text-critical">{error}</p>}
      <button type="submit" disabled={busy} className="inline-flex min-h-11 items-center rounded-lg bg-action px-4 text-sm font-semibold text-white disabled:opacity-50">
        {busy ? "Saving" : "Save decision"}
      </button>
    </form>
  );
}
