import { CockpitTabs } from "@/components/shell/CockpitTabs";
import { ReleaseChrome } from "@/components/shell/ReleaseChrome";
import { stageOf } from "@/components/shell/model";
import { releaseFromParams, releaseList } from "@/lib/release-page";
import { groupByProject } from "@/lib/routes";

export default async function ReleaseLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ project: string; name: string }>;
}) {
  const release = await releaseFromParams(params);
  const groups = groupByProject(await releaseList()).map((g) => ({
    slug: g.slug,
    displayName: g.displayName,
    releases: g.releases.map((r) => r.name),
    lab: g.releases.some((r) => r.has_lab),
  }));
  return (
    <div className="mx-auto max-w-[1400px] space-y-5">
      <ReleaseChrome
        groups={groups}
        project={release.project.toLowerCase()}
        release={release.name}
        displayName={release.display_name || release.project}
        hasLab={release.has_lab}
        stage={stageOf(release, new Date(release.as_of))}
        codeFreezeAt={release.code_freeze_at}
        releaseAt={release.release_at}
        asOf={release.as_of}
      />
      <CockpitTabs project={release.project} release={release.name} />
      <div className="min-w-0">{children}</div>
    </div>
  );
}
