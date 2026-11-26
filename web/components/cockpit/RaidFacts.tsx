// Three RAID counts on the Live Cockpit. Each one links to the release RAID page.
import Link from "next/link";
import type { RaidSummary } from "@/lib/api-raid";
import { NO_MEETING_NOTES, raidFacts } from "@/lib/raid-facts";

export function RaidFacts({ summary, href }: { summary: RaidSummary; href: string }) {
  const facts = raidFacts(summary);
  return (
    <section className="rounded-2xl border border-slate-200 bg-white px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-heading text-lg font-semibold">RAID</h2>
        {summary.synthetic && <p className="rounded-full bg-warning-bg px-3 py-1 text-sm font-medium text-warning">Synthetic data</p>}
      </div>
      {facts === null ? (
        <p className="mt-3 text-sm text-slate-600">{NO_MEETING_NOTES}</p>
      ) : (
        <ul className="mt-3 flex flex-wrap gap-3">
          {facts.map((fact) => (
            <li key={fact.label}>
              <Link href={href} className="inline-flex min-h-11 items-center rounded-lg bg-slate-50 px-4 text-sm font-semibold text-action hover:underline">
                {fact.count} {fact.label}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
