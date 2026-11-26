// RAID for one release: the review queue and the confirmed tracker.
import { RaidTabs } from "@/components/raid/RaidTabs";
import { ErrorState } from "@/components/states/States";
import { ApiError } from "@/lib/api-http";
import { fetchRaid, fetchRaidQueue, fetchRaidSummary, type RaidList, type RaidSummary } from "@/lib/api-raid";
import { releaseFromParams } from "@/lib/release-page";

export const dynamic = "force-dynamic";

export default async function RaidPage({ params }: { params: Promise<{ project: string; name: string }> }) {
  const release = await releaseFromParams(params);
  let queue: RaidList;
  let summary: RaidSummary;
  let tracker: RaidList;
  try {
    [queue, summary, tracker] = await Promise.all([
      fetchRaidQueue(release.project, release.name),
      fetchRaidSummary(release.project, release.name),
      fetchRaid(release.project, release.name),
    ]);
  } catch (e) {
    const detail = e instanceof ApiError ? e.message : "The RAID API failed";
    return <ErrorState title="RAID could not be loaded" detail={detail} />;
  }
  return <RaidTabs queue={queue} summary={summary} tracker={tracker} />;
}
