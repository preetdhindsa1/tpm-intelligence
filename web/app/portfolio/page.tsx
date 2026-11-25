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
  if (!data) return <ErrorState title="Portfolio could not be loaded" detail={message} />;
  return <PortfolioView data={data} />;
}
