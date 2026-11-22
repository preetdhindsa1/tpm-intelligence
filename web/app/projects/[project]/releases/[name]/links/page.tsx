import { releaseFromParams } from "@/lib/release-page";
import { releasePath } from "@/lib/routes";
import Link from "next/link";
import { LinkQueue } from "@/components/LinkQueue";

export const dynamic = "force-dynamic";

export default async function LinksPage({ params }: { params: Promise<{ project: string; name: string }> }) {
  const release = await releaseFromParams(params);
  const name = release.name;
  const project = release.project;
  return (
    <div className="space-y-4">
      <div>
        <Link href={releasePath(project, name)} className="text-sm text-indigo-700 hover:underline">← {name} release health</Link>
        <h1 className="text-2xl font-semibold">Link review · {release.display_name || release.project} {name}</h1>
        <p className="text-sm text-slate-600">
          AI suggests which feature an unlinked pull request is work for. A suggestion never counts in the facts or the
          forecast until you confirm it here.
        </p>
      </div>
      <LinkQueue release={name} />
    </div>
  );
}
