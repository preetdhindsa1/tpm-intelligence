import { FeatureTable } from "@/components/dashboard/FeatureTable";
import { ReleaseHeader } from "@/components/dashboard/ReleaseHeader";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ReportsPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const data = await api.features(name);
  const current = data.features.filter((f) => f.in_release);
  const removed = data.features.filter((f) => !f.in_release);

  return (
    <div className="flex min-h-screen flex-col">
      <ReleaseHeader
        releaseName={name}
        release={data.release}
        title="Reports"
        subtitle="Feature health table · flags, odds, and linked PRs"
      />
      <div className="space-y-4 p-4">
        {!data.validation.validated ? (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
            <strong>Odds are not validated.</strong> {data.validation.reason}
          </div>
        ) : null}
        <FeatureTable title={`In the release (${current.length})`} rows={current} release={name} />
        {removed.length ? (
          <FeatureTable title={`Removed from the release (${removed.length})`} rows={removed} release={name} />
        ) : null}
      </div>
    </div>
  );
}
