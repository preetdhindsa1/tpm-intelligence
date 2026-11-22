import { ReleaseSwitcher } from "@/components/ReleaseSwitcher";
import { Sidebar } from "@/components/Sidebar";
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
  return (
    <div className="space-y-4">
      <ReleaseSwitcher groups={groups} project={release.project.toLowerCase()} release={release.name} />
      <div className="flex gap-6">
        <aside className="hidden w-44 shrink-0 md:block">
          <Sidebar project={release.project} release={release.name} />
        </aside>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
