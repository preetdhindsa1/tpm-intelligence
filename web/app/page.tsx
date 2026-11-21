import { redirect } from "next/navigation";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  const releases = await api.releases();
  const latest = releases.at(-1);
  redirect(latest ? `/releases/${latest.name}` : "/releases/v1.38");
}
