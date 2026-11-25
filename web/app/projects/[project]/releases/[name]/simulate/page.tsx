import { Simulator } from "@/components/Simulator";
import { programTitle } from "@/lib/names";
import { releaseFromParams } from "@/lib/release-page";
import { releasePath } from "@/lib/routes";

export const dynamic = "force-dynamic";

// Decision Studio. The title, stage and dates are in the release layout's header.
export default async function SimulatePage({ params }: { params: Promise<{ project: string; name: string }> }) {
  const release = await releaseFromParams(params);
  const title = programTitle(release.display_name || release.project, release.name, release.has_lab);
  return <Simulator release={release.name} program={title} cockpit={releasePath(release.project, release.name)} freezeLabel={release.code_freeze_label} />;
}
