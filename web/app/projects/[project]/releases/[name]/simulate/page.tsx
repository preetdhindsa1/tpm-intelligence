import { Simulator } from "@/components/Simulator";
import { releaseFromParams } from "@/lib/release-page";
import { releasePath } from "@/lib/routes";

export const dynamic = "force-dynamic";

// Decision Studio. The title, stage and dates are in the release layout's header.
export default async function SimulatePage({ params }: { params: Promise<{ project: string; name: string }> }) {
  const release = await releaseFromParams(params);
  return <Simulator release={release.name} cockpit={releasePath(release.project, release.name)} />;
}
