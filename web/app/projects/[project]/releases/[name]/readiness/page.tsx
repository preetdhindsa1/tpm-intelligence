import { ReadinessView } from "@/components/readiness/ReadinessView";
import { ErrorState } from "@/components/states/States";
import { ApiError } from "@/lib/api-http";
import { fetchReadiness, type Readiness } from "@/lib/api-readiness";
import { releaseFromParams } from "@/lib/release-page";

export const dynamic = "force-dynamic";

export default async function ReadinessPage({ params }: { params: Promise<{ project: string; name: string }> }) {
  const release = await releaseFromParams(params);
  let data: Readiness;
  try {
    data = await fetchReadiness(release.name);
  } catch (e) {
    const detail = e instanceof ApiError ? e.message : "The readiness API failed";
    return <ErrorState title="Readiness could not be loaded" detail={detail} />;
  }
  return <ReadinessView data={data} />;
}
