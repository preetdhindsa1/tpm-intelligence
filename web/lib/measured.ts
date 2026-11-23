// Measured results shown on the front page. Copied from README.md "Measured results"
// (the source of truth); every entry carries its date and how to read it. Results that
// failed are shown too: measure, don't claim (CLAUDE.md section 2).

export type Verdict = "pass" | "partial" | "fail" | "pending";

export type Measured = {
  id: string;
  label: string;
  value: string;
  detail: string;
  verdict: Verdict;
  measured: string; // YYYY-MM-DD, or "" when not measured yet
};

export const MEASURED: Measured[] = [
  {
    id: "fact-checker",
    label: "Fact checker agrees with labelled claims",
    value: "43 / 43",
    detail: "22 verified, 21 removed across all 5 reasons. Labels proposed by the developer, pending TPM review.",
    verdict: "pass",
    measured: "2026-11-22",
  },
  {
    id: "linking",
    label: "Tracked v1.38 features with a verified PR",
    value: "68 / 69",
    detail: "Coverage counts whether a link exists, not whether it is right. Precision per method: not yet labelled.",
    verdict: "pass",
    measured: "2026-11-21",
  },
  {
    id: "kafka-linking",
    label: "Kafka 4.4.0 features with a verified PR (Jira plan)",
    value: "21 / 26",
    detail: "Same engine on Apache Kafka: Jira keys, remote links, sub-task PRs rolled up to umbrellas (89 links). Precision not labelled yet.",
    verdict: "pass",
    measured: "2026-11-23",
  },
  {
    id: "risk-analyst",
    label: "Risk analyst claims removed by the checker",
    value: "4.0%",
    detail: "12 real v1.37/v1.38 cases, critical-flag coverage 100%, $0.024 per run. Small sample.",
    verdict: "pass",
    measured: "2026-11-22",
  },
  {
    id: "vp-summary",
    label: "VP summary claims removed by the checker",
    value: "0%",
    detail: "4 real release fact sheets, at most 217 words, about $0.14 per draft. Small sample.",
    verdict: "pass",
    measured: "2026-11-22",
  },
  {
    id: "link-suggester",
    label: "AI link suggester precision",
    value: "84.8%",
    detail: "60 hidden-key cases, recall 70%. Suggestions never count until a person confirms them.",
    verdict: "partial",
    measured: "2026-11-22",
  },
  {
    id: "forecast",
    label: "Forecast beats the base rate",
    value: "9 of 12",
    detail: "Backtests v1.35–v1.38 at 28/14/7 days before freeze. Not every case, so odds stay labelled \"not validated\".",
    verdict: "partial",
    measured: "2026-11-22",
  },
  {
    id: "simulator",
    label: "What-if simulator within ±20% on replay",
    value: "Not validated",
    detail: "Median review wait off by +205% (v1.37) and +350% (v1.38); time to merge within range. Shown with a warning.",
    verdict: "fail",
    measured: "2026-11-22",
  },
  {
    id: "merge-dates",
    label: "Merge-date forecasts beat the baseline",
    value: "3 of 12",
    detail: "Ranges are about the right width (75–92% coverage), but the forecast beats a simple baseline in only 3 of 12 backtests. Shown as not validated.",
    verdict: "fail",
    measured: "2026-11-22",
  },
  {
    id: "unseen-test",
    label: "First unseen test: v1.39, scored on forecasts recorded while it runs",
    value: "TBD",
    detail: "Model frozen and rules fixed in advance (ADR-0015). Forecasts are stored daily and can never be edited.",
    verdict: "pending",
    measured: "",
  },
  {
    id: "data-freshness",
    label: "Data freshness, polled Kubernetes (target under 10 min)",
    value: "< 9 min",
    detail: "24 of 24 polls succeeded every 5 minutes over 2 hours. Longest gap between successful polls 6.2 min.",
    verdict: "pass",
    measured: "2026-11-23",
  },
  {
    id: "freshness",
    label: "Stored event → live page in the cloud (p95)",
    value: "15.9 s",
    detail: "Recompute p95 9.2 s (was about 56 s). Excludes the wait for the next poll; the webhook path (target 30 s end to end) is not measured yet. Small sample.",
    verdict: "partial",
    measured: "2026-11-23",
  },
];
