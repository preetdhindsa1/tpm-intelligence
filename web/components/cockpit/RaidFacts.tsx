// Three RAID counts on the Live Cockpit. Each one links to the release RAID page.
import Link from "next/link";
import type { RaidSummary } from "@/lib/api-raid";
import { raidFacts } from "@/lib/raid-facts";

export function RaidFacts({ summary, href }: { summary: RaidSummary; href: string }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-heading text-lg font-semibold">RAID</h2>
        {summary.synthetic && <p className="rounded-full bg-warning-bg px-3 py-1 text-sm font-medium text-warning">Synthetic data</p>}
      </div>
      <ul className="mt-3 flex flex-wrap gap-3">
        {raidFacts(summary).map((fact) => (
          <li key={fact.label}>
            <Link href={href} className="inline-flex min-h-11 items-center rounded-lg bg-slate-50 px-4 text-sm font-semibold text-action hover:underline">
              {fact.count} {fact.label}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
