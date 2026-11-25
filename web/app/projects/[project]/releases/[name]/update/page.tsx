import { releaseFromParams } from "@/lib/release-page";
import { ExecUpdatePanel } from "@/components/ExecUpdate";

export const dynamic = "force-dynamic";

export default async function UpdatePage({ params }: { params: Promise<{ project: string; name: string }> }) {
  const release = await releaseFromParams(params);
  const name = release.name;
  return (
    <div className="space-y-4">
      <div>
        <h1 className="font-heading text-2xl font-semibold">Executive update · {release.display_name || release.project} {name}</h1>
        <p className="text-sm text-slate-600">
          AI drafts, the fact checker verifies every claim, you edit and approve. Nothing is ever sent from here.
        </p>
      </div>
      <ExecUpdatePanel release={name} />
    </div>
  );
}
