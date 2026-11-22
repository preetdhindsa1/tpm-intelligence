// Old links (/releases/v1.38/...) from before release URLs carried the project
// (ADR-0014). Redirect when exactly one project has a release with this name.
import { notFound, redirect } from "next/navigation";
import { api } from "@/lib/api";
import { projectSlug, releasePath } from "@/lib/routes";

export const dynamic = "force-dynamic";

export default async function LegacyRelease({ params }: { params: Promise<{ name: string; rest?: string[] }> }) {
  const { name, rest } = await params;
  const matches = (await api.releases()).filter((r) => r.name === decodeURIComponent(name));
  if (matches.length === 0) notFound();
  if (matches.length > 1) redirect("/");
  redirect(releasePath(projectSlug(matches[0]), matches[0].name, rest?.length ? `/${rest.join("/")}` : ""));
}
