import Link from "next/link";
import { LinkQueue } from "@/components/LinkQueue";

export const dynamic = "force-dynamic";

export default async function LinksPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  return (
    <div className="space-y-4">
      <div>
        <Link href={`/releases/${name}`} className="text-sm text-indigo-700 hover:underline">← {name} release health</Link>
        <h1 className="text-2xl font-semibold">Link review · Kubernetes {name}</h1>
        <p className="text-sm text-slate-600">
          AI suggests which feature an unlinked pull request is work for. A suggestion never counts in the facts or the
          forecast until you confirm it here.
        </p>
      </div>
      <LinkQueue release={name} />
    </div>
  );
}
