import type { Release } from "@/lib/api";
import { formatUtc } from "@/lib/format";
import { LiveRefresh } from "@/components/LiveRefresh";

export function ReleaseHeader({
  releaseName,
  release,
  title,
  subtitle,
}: {
  releaseName: string;
  release: Release;
  title: string;
  subtitle?: string;
}) {
  const label = `${release.display_name || release.project || "Team"} ${release.name}`;
  return (
    <header className="flex flex-wrap items-end justify-between gap-3 border-b border-[var(--tpm-line)] bg-white px-5 py-4">
      <div>
        <p className="text-[11px] uppercase tracking-wide text-[var(--tpm-muted)]">{title}</p>
        <h1 className="text-xl font-semibold tracking-tight">{label}</h1>
        <p className="text-sm text-[var(--tpm-muted)]">
          {subtitle ??
            `Code Freeze ${release.code_freeze_at ? formatUtc(release.code_freeze_at) : "unknown"} · ${release.features_in_release} in release · as of ${formatUtc(release.as_of)}`}
        </p>
      </div>
      <LiveRefresh release={releaseName} />
    </header>
  );
}
