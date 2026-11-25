import { CockpitTabs } from "@/components/shell/CockpitTabs";
import { ReleaseChrome } from "@/components/shell/ReleaseChrome";
import { stageOf } from "@/components/shell/model";
import { formatUtc } from "@/lib/format";
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
  }));
  const when = (iso: string | null) => (iso ? formatUtc(iso) : "unknown");
  return (
    <div className="space-y-4">
      <ReleaseChrome
        groups={groups}
        project={release.project.toLowerCase()}
        release={release.name}
        displayName={release.display_name || release.project}
        stage={stageOf(release, new Date(release.as_of))}
        codeFreeze={when(release.code_freeze_at)}
        releaseAt={when(release.release_at)}
        asOf={formatUtc(release.as_of)}
      />
      <CockpitTabs project={release.project} release={release.name} />
      <div className="min-w-0">{children}</div>
    </div>
  );
}
