import { DependencyGraph } from "@/components/dashboard/DependencyGraph";
import { ReleaseHeader } from "@/components/dashboard/ReleaseHeader";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DependenciesPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const data = await api.features(name);
  const label = `${data.release.display_name || data.release.project || "Team"} ${data.release.name}`;

  return (
    <div className="flex min-h-screen flex-col">
      <ReleaseHeader
        releaseName={name}
        release={data.release}
        title="Dependencies"
        subtitle="Feature graph by SIG lane · critical flags highlighted"
      />
      <div className="min-h-[calc(100vh-6rem)] flex-1 p-4">
        <div className="h-[calc(100vh-8rem)] min-h-[32rem]">
          <DependencyGraph features={data.features} releaseLabel={label} />
        </div>
      </div>
    </div>
  );
}
