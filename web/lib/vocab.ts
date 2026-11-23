// Words that differ by project (ADR-0018). Kubernetes plans in KEPs owned by SIGs and
// numbers features "#6395"; Kafka plans in Jira ("KAFKA-20682"), designs in KIPs and is
// split into components. Teams are counted per team, never per person.

/** Short feature name: "#6395" for a GitHub issue, the Jira key itself otherwise. */
export function featureLabel(f: { key: string; number: number }): string {
  return f.key.includes("#") ? `#${f.number}` : f.key;
}

// `tracking`: the project's release team marks features tracked (Kubernetes "tracked/yes").
// `sample`: invented demo data (ADR-0020); every page says so.
export type Vocab = {
  team: string;
  teams: string;
  design: string;
  designs: string;
  tracking: boolean;
  sample?: boolean;
};

const VOCAB: Record<string, Vocab> = {
  kubernetes: { team: "SIG", teams: "SIGs", design: "KEP", designs: "KEPs", tracking: true },
  kafka: { team: "component", teams: "components", design: "KIP", designs: "KIPs", tracking: false },
  demo: { team: "team", teams: "teams", design: "issue", designs: "issues", tracking: false, sample: true },
};

const GENERIC: Vocab = { team: "team", teams: "teams", design: "design doc", designs: "design docs", tracking: false };

/** Vocabulary for a project slug or key ("kafka", "KAFKA"). */
export function vocab(project: string): Vocab {
  return VOCAB[project.toLowerCase()] ?? GENERIC;
}

/** Team label without its prefix ("sig/node" -> "node"). */
export function shortTeam(t: string): string {
  return t.replace(/^sig\//, "");
}
