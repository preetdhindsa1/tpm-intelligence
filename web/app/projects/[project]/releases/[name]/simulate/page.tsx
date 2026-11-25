import { Simulator } from "@/components/Simulator";
import { releaseFromParams } from "@/lib/release-page";

export const dynamic = "force-dynamic";

export default async function SimulatePage({ params }: { params: Promise<{ project: string; name: string }> }) {
  const release = await releaseFromParams(params);
  const name = release.name;
  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm text-slate-600">
          Pick a reviewer pool and one lever. Baseline and scenario stay illustrative until a run fills them from the simulator.
          Results are ranges, not guarantees.
        </p>
      </div>
      <Simulator release={name} />
    </div>
  );
}
