import { DependencyGraph } from "@/components/DependencyGraph";
import { api } from "@/lib/api";
import { formatUtc } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function DependenciesPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const graph = await api.graph(name);
  return (
    <div className="space-y-3">
      <div>
        <h1 className="text-2xl font-semibold">Dependencies · Kubernetes {name}</h1>
        <p className="text-sm text-slate-600">
          Release → features → their verified PRs, with &quot;depends on&quot; links stated in PR text. KEPs have no machine-readable
          dependency field, so most chains are short: the graph shows what the data says, nothing deeper. Click a feature to
          open it, or a PR to open it on GitHub. Data as of {formatUtc(graph.as_of)}.
        </p>
      </div>
      <div className="h-[calc(100vh-220px)] min-h-[520px] rounded-lg border bg-white p-3 shadow-sm">
        <DependencyGraph release={name} data={graph} />
      </div>
    </div>
  );
}
