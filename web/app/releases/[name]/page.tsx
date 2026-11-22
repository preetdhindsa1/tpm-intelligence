import { ReleaseDashboard } from "@/components/dashboard/ReleaseDashboard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DashboardPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const data = await api.features(name);

  return (
    <ReleaseDashboard
      releaseName={name}
      release={data.release}
      features={data.features}
      validation={data.validation}
    />
  );
}
