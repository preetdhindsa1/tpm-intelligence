import { PortfolioView } from "@/components/portfolio/PortfolioView";
import { ErrorState } from "@/components/states/States";
import { api } from "@/lib/api";
import type { Portfolio } from "@/lib/portfolio";

export const dynamic = "force-dynamic";

export default async function PortfolioPage() {
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
        <h1 className="text-2xl font-semibold">Here are the live programs.</h1>
        <ErrorState title="Portfolio could not be loaded" detail={message} />
      </div>
    );
  }
  return <PortfolioView data={data} />;
}
