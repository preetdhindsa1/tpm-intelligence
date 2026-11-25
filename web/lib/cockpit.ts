// Stops for the #6395 time machine. Dates come from the feature timeline, never from this file.
export type TimelineStop = { at: string; kind: string; ref: string | null };

const STORY = new Set([
  "opted_in",
  "tracked",
  "untracked",
  "added_to_release",
  "removed_from_release",
  "enhancements_freeze",
  "code_freeze",
  "pr_opened",
  "pr_merged",
  "pr_closed",
]);

export function storyStops(events: TimelineStop[]): TimelineStop[] {
  const seen = new Set<string>();
  const stops: TimelineStop[] = [];
  for (const event of events) {
    if (!STORY.has(event.kind)) continue;
    const key = `${event.at}\0${event.kind}\0${event.ref ?? ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    stops.push(event);
  }
  return stops;
}
