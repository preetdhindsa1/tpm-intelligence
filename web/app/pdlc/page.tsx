import { PdlcView } from "@/components/pdlc/PdlcView";
import { formatUtc } from "@/lib/format";
import { fetchPodLab, type PodLab } from "@/lib/api-pdlc";

export const dynamic = "force-dynamic";

export default async function PdlcPage() {
  let lab: PodLab | null = null;
  let error = "";
  try {
    lab = await fetchPodLab();
  } catch (e) {
    error = e instanceof Error ? e.message : "GET /lab failed";
  }
  if (!lab?.pod) {
    return (
      <section className="space-y-2">
        <h1 className="text-2xl font-semibold">How the pod builds, checks and ships</h1>
        <p className="text-sm text-slate-600">
          {error ? `Pod facts could not be loaded. ${error}` : "Pod facts are not available from this API yet."} No
          example numbers are shown instead.
        </p>
      </section>
    );
  }
  return <PdlcView pod={lab.pod} asOf={formatUtc(lab.as_of)} total={lab.n_pull_requests} merged={lab.n_merged} />;
}
