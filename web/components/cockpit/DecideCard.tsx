import Link from "next/link";

export function DecideCard({ href, reason }: { href: string; reason: string | null }) {
  return (
    <section className="rounded-lg border bg-white p-4">
      <h2 className="font-semibold text-slate-800">Decide</h2>
      {reason && <p className="mt-1 text-sm text-warning">Not validated. {reason}</p>}
      <Link href={href} className="mt-2 inline-flex min-h-11 items-center text-sm font-medium text-action hover:underline">Open Decision Studio</Link>
    </section>
  );
}
