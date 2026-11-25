import { PortfolioView } from "@/components/portfolio/PortfolioView";
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
      <section>
        <h1 className="text-2xl font-semibold">Here are the live programs.</h1>
        <p className="mt-2 text-sm text-slate-600">Portfolio could not be loaded. {message}</p>
      </section>
    );
  }
  return <PortfolioView data={data} />;
}
