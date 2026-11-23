// Words that differ by project (ADR-0018). Kubernetes plans in KEPs owned by SIGs and
// numbers features "#6395"; Kafka plans in Jira ("KAFKA-20682"), designs in KIPs and is
// split into components. Teams are counted per team, never per person.

/** Short feature name: "#6395" for a GitHub issue, the Jira key itself otherwise. */
export function featureLabel(f: { key: string; number: number }): string {
  return f.key.includes("#") ? `#${f.number}` : f.key;
}

export type Vocab = { team: string; teams: string; design: string; designs: string };

const VOCAB: Record<string, Vocab> = {
  kubernetes: { team: "SIG", teams: "SIGs", design: "KEP", designs: "KEPs" },
  kafka: { team: "component", teams: "components", design: "KIP", designs: "KIPs" },
};

const GENERIC: Vocab = { team: "team", teams: "teams", design: "design doc", designs: "design docs" };

/** Vocabulary for a project slug or key ("kafka", "KAFKA"). */
export function vocab(project: string): Vocab {
  return VOCAB[project.toLowerCase()] ?? GENERIC;
}

/** Team label without its prefix ("sig/node" -> "node"). */
export function shortTeam(t: string): string {
  return t.replace(/^sig\//, "");
}
