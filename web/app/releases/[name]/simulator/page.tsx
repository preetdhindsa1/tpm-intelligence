import { ReleaseHeader } from "@/components/dashboard/ReleaseHeader";
import { SimulatorPanel } from "@/components/dashboard/SimulatorPanel";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SimulatorPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const data = await api.features(name);

  return (
    <div className="flex min-h-screen flex-col">
      <ReleaseHeader
        releaseName={name}
        release={data.release}
        title="Simulator"
        subtitle="Shadow-Org what-ifs · calibrated on measured data once Phase 2 validation passes"
      />
      <SimulatorPanel features={data.features} validation={data.validation} />
    </div>
  );
}
