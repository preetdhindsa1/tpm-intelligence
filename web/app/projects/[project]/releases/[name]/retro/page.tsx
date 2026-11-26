import { RetroView } from "@/components/retro/RetroView";
import { ErrorState } from "@/components/states/States";
import { ApiError } from "@/lib/api-http";
import { fetchPatterns, fetchRetro, fetchSaidVsShowed, type Patterns, type Retro, type SaidVsShowed } from "@/lib/api-readiness";
import { releaseFromParams } from "@/lib/release-page";
import { NOT_COMPUTED, isMissingRetro } from "@/lib/retro";

export const dynamic = "force-dynamic";

export default async function RetroPage({ params }: { params: Promise<{ project: string; name: string }> }) {
  const release = await releaseFromParams(params);
  let retro: Retro;
  try {
    retro = await fetchRetro(release.project, release.name);
  } catch (e) {
    if (e instanceof ApiError && isMissingRetro(e.status)) {
      return <p className="text-sm text-slate-600">{NOT_COMPUTED}</p>;
    }
    const detail = e instanceof ApiError ? e.message : "The retro API failed";
    return <ErrorState title="Retro could not be loaded" detail={detail} />;
  }
  let patterns: Patterns | null = null;
  try {
    patterns = await fetchPatterns(release.project);
  } catch {
    patterns = null;
  }
  let said: SaidVsShowed | null = null;
  try {
    said = await fetchSaidVsShowed(release.project, release.name);
  } catch {
    said = null;
  }
  return <RetroView retro={retro} patterns={patterns} said={said} />;
}
