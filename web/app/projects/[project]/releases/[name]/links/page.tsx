import { releaseFromParams } from "@/lib/release-page";
import { LinkQueue } from "@/components/LinkQueue";

export const dynamic = "force-dynamic";

export default async function LinksPage({ params }: { params: Promise<{ project: string; name: string }> }) {
  const release = await releaseFromParams(params);
  const name = release.name;
  return (
    <div className="space-y-4">
      <div>
        <h1 className="font-heading text-2xl font-semibold">Link review · {release.display_name || release.project} {name}</h1>
        <p className="text-sm text-slate-600">
          AI suggests which feature an unlinked pull request is work for. A suggestion never counts in the facts or the
          forecast until you confirm it here.
        </p>
      </div>
      <LinkQueue release={name} />
    </div>
  );
}
