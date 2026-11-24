"use client";

import { useRouter } from "next/navigation";

export type LabGroup = { slug: string; displayName: string; releases: string[] };

const OWN = "tpm-intelligence";

/** Project, and for Kubernetes or Kafka the release. Stays on /lab. */
export function LabPicker({
  groups,
  project,
  release,
}: {
  groups: LabGroup[];
  project: string;
  release: string | null;
}) {
  const router = useRouter();
  const group = groups.find((g) => g.slug === project);
  const names = group ? [...group.releases].reverse() : [];

  function chooseProject(slug: string) {
    if (slug === OWN) {
      router.push(`/lab?project=${OWN}`);
      return;
    }
    const next = groups.find((g) => g.slug === slug);
    const newest = next ? [...next.releases].reverse()[0] : "";
    router.push(`/lab?project=${encodeURIComponent(slug)}&release=${encodeURIComponent(newest ?? "")}`);
  }

  return (
    <div className="flex flex-wrap items-end gap-3 text-sm">
      <label className="flex flex-col gap-1 text-slate-600">
        Project
        <select
          aria-label="Project"
          className="rounded-md border bg-white px-2 py-1 text-slate-900"
          value={project}
          onChange={(e) => chooseProject(e.target.value)}
        >
          {groups.map((g) => (
            <option key={g.slug} value={g.slug}>
              {g.displayName}
            </option>
          ))}
        </select>
      </label>
      {project !== OWN && (
        <label className="flex flex-col gap-1 text-slate-600">
          Release
          <select
            aria-label="Release"
            className="rounded-md border bg-white px-2 py-1 text-slate-900"
            value={release ?? ""}
            onChange={(e) =>
              router.push(`/lab?project=${encodeURIComponent(project)}&release=${encodeURIComponent(e.target.value)}`)
            }
          >
            {names.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}
