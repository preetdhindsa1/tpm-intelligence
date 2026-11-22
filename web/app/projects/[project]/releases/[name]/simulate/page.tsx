import { releaseFromParams } from "@/lib/release-page";
import { releasePath } from "@/lib/routes";
import Link from "next/link";
import { Simulator } from "@/components/Simulator";

export const dynamic = "force-dynamic";

export default async function SimulatePage({ params }: { params: Promise<{ project: string; name: string }> }) {
  const release = await releaseFromParams(params);
  const name = release.name;
  const project = release.project;
  return (
    <div className="space-y-4">
      <div>
        <Link href={releasePath(project, name)} className="text-sm text-indigo-700 hover:underline">← {name} release health</Link>
        <h1 className="text-2xl font-semibold">What-if simulator · {release.display_name || release.project} {name}</h1>
        <p className="text-sm text-slate-600">
          Change reviewer staffing, interruptions or the flow of new PRs and see the effect on review waits and merges, next to
          the baseline. Results are ranges from a model calibrated on past releases, not guarantees.
        </p>
      </div>
      <Simulator release={name} />
    </div>
  );
}
