// Server-side lookup for project-scoped release pages: resolves /projects/{p}/releases/{n}
// to a known release or a 404. The release list is cheap (no forecast) and memoised per
// request, so the layout and the page share one call.
import { notFound } from "next/navigation";
import { cache } from "react";
import { api, type Release } from "@/lib/api";
import { findRelease } from "@/lib/routes";

export const releaseList = cache(() => api.releases());

export async function releaseFromParams(params: Promise<{ project: string; name: string }>): Promise<Release> {
  const { project, name } = await params;
  const r = findRelease(await releaseList(), project, name);
  if (!r) notFound();
  return r;
}
