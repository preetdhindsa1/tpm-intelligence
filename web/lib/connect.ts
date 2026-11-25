// Connect page copy. No customer counts: sign-up is a later wave, and this page
// only describes the sources the public demo already reads.

export const STEPS = [
  {
    title: "Connect",
    body: "Point the platform at the planning tool and the code host. It reads them. It does not write back.",
  },
  {
    title: "Describe releases",
    body: "Give each release its cycle start, Enhancements Freeze, Code Freeze, and release date. The stage uses cycle start, Code Freeze, and the release date.",
  },
  {
    title: "First program filling in",
    body: "The public demo is already filling in from Kubernetes, Apache Kafka, and this repository. A company's own program is not available from this page yet.",
  },
] as const;

export const CONNECTORS = [
  {
    name: "GitHub",
    usedFor: "Kubernetes planning and code, Apache Kafka code, and this repository",
    status: "Used in the public demo",
  },
  {
    name: "Jira",
    usedFor: "Apache Kafka planning",
    status: "Used in the public demo",
  },
] as const;

export const PROMISES = [
  {
    title: "Read-only",
    body: "Every source is read with a read-only scope. The platform does not change the source system.",
  },
  {
    title: "A person approves",
    body: "An executive update, a published tracker, or a readiness decision leaves only after a person approves it.",
  },
  {
    title: "Public demo privacy",
    body: "The public demo shows roles and counts, not people's usernames.",
  },
] as const;
