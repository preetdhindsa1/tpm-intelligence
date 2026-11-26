// RAID review queue for one release. The tracker is a later tab; this page is the queue.
import { ReviewQueue } from "@/components/raid/ReviewQueue";
import { ErrorState } from "@/components/states/States";
import { ApiError } from "@/lib/api-http";
import { fetchRaidQueue, fetchRaidSummary, type RaidList, type RaidSummary } from "@/lib/api-raid";
import { releaseFromParams } from "@/lib/release-page";

export const dynamic = "force-dynamic";

export default async function RaidPage({ params }: { params: Promise<{ project: string; name: string }> }) {
  const release = await releaseFromParams(params);
  let queue: RaidList;
  let summary: RaidSummary;
  try {
    [queue, summary] = await Promise.all([
      fetchRaidQueue(release.project, release.name),
      fetchRaidSummary(release.project, release.name),
    ]);
  } catch (e) {
    const detail = e instanceof ApiError ? e.message : "The RAID API failed";
    return <ErrorState title="RAID could not be loaded" detail={detail} />;
  }
  return <ReviewQueue queue={queue} summary={summary} />;
}
