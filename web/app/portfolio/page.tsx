import { PortfolioView } from "@/components/portfolio/PortfolioView";
import { ErrorState } from "@/components/states/States";
import { api } from "@/lib/api";
import { fetchRaidSummary } from "@/lib/api-raid";
import { STAGE_NAMES, withRaidWaiting, type Portfolio } from "@/lib/portfolio";

export const dynamic = "force-dynamic";

export default async function PortfolioPage({ searchParams }: { searchParams: Promise<{ stage?: string }> }) {
  const { stage } = await searchParams;
  let data: Portfolio | null = null;
  let message = "GET /portfolio failed";
  try {
    data = await api.portfolio();
  } catch (e) {
    message = e instanceof Error ? e.message : message;
  }
  if (!data) {
    return (
      <div className="space-y-4">
        <h1 className="font-heading text-4xl font-bold tracking-tight">Here are the live programs.</h1>
        <ErrorState title="Portfolio could not be loaded" detail={message} />
      </div>
    );
  }
  const counts = (
    await Promise.all(
      data.programs.map(async (program) => {
        try {
          const summary = await fetchRaidSummary(program.project, program.release);
          return { key: program.key, waiting_for_review: summary.waiting_for_review };
        } catch {
          return null;
        }
      }),
    )
  ).filter((row): row is { key: string; waiting_for_review: number } => row !== null);
  const waiting = withRaidWaiting(data.waiting_on_you, data.programs, counts);
  return (
    <PortfolioView
      data={{ ...data, waiting_on_you: waiting, totals: { ...data.totals, waiting_on_you: waiting.length } }}
      stage={stage && STAGE_NAMES.includes(stage as (typeof STAGE_NAMES)[number]) ? stage : null}
    />
  );
}
