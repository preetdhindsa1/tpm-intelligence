import Link from "next/link";
import { ExecUpdatePanel } from "@/components/ExecUpdate";

export const dynamic = "force-dynamic";

export default async function UpdatePage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  return (
    <div className="space-y-4">
      <div>
        <Link href={`/releases/${name}`} className="text-sm text-indigo-700 hover:underline">← {name} release health</Link>
        <h1 className="text-2xl font-semibold">Executive update · Kubernetes {name}</h1>
        <p className="text-sm text-slate-600">
          AI drafts, the fact checker verifies every claim, you edit and approve. Nothing is ever sent from here.
        </p>
      </div>
      <ExecUpdatePanel release={name} />
    </div>
  );
}
