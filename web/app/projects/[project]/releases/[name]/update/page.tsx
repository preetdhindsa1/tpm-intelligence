import { releaseFromParams } from "@/lib/release-page";
import { releasePath } from "@/lib/routes";
import Link from "next/link";
import { ExecUpdatePanel } from "@/components/ExecUpdate";

export const dynamic = "force-dynamic";

export default async function UpdatePage({ params }: { params: Promise<{ project: string; name: string }> }) {
  const release = await releaseFromParams(params);
  const name = release.name;
  const project = release.project;
  return (
    <div className="space-y-4">
      <div>
        <Link href={releasePath(project, name)} className="text-sm text-indigo-700 hover:underline">← {name} release health</Link>
        <h1 className="text-2xl font-semibold">Executive update · {release.display_name || release.project} {name}</h1>
        <p className="text-sm text-slate-600">
          AI drafts, the fact checker verifies every claim, you edit and approve. Nothing is ever sent from here.
        </p>
      </div>
      <ExecUpdatePanel release={name} />
    </div>
  );
}
