// Team cards on the front page. A card is "Live" when the API serves a project whose
// display name (connectors/teams/<id>.yaml) equals the card's name.

export const SELF_PROJECT = "Program Intelligence Platform (Current Project)";

export function teamState(name: string, live: ReadonlySet<string>): string {
  if (live.has(name)) return "Live";
  if (name === SELF_PROJECT) return "Built · waiting for the first issues";
  if (name === "Apache Kafka") return "Connector configured · data not yet collected";
  return "Plug in";
}
