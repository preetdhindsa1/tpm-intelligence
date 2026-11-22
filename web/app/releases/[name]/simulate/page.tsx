import Link from "next/link";
import { Simulator } from "@/components/Simulator";

export const dynamic = "force-dynamic";

export default async function SimulatePage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  return (
    <div className="space-y-4">
      <div>
        <Link href={`/releases/${name}`} className="text-sm text-indigo-700 hover:underline">← {name} release health</Link>
        <h1 className="text-2xl font-semibold">What-if simulator · Kubernetes {name}</h1>
        <p className="text-sm text-slate-600">
          Change reviewer staffing, interruptions or the flow of new PRs and see the effect on review waits and merges, next to
          the baseline. Results are ranges from a model calibrated on past releases, not guarantees.
        </p>
      </div>
      <Simulator release={name} />
    </div>
  );
}
