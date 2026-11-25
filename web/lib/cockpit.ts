// Stops for the #6395 time machine. Dates come from the feature timeline, never from this file.
export type TimelineStop = { at: string; kind: string; ref: string | null };

const STORY = new Set([
  "opted_in",
  "tracked",
  "untracked",
  "added_to_release",
  "removed_from_release",
  "code_freeze",
  "pr_opened",
  "pr_merged",
  "pr_closed",
]);

export function storyStops(events: TimelineStop[]): TimelineStop[] {
  return events.filter((e) => STORY.has(e.kind));
}
