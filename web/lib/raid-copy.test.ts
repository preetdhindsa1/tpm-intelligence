import { describe, expect, it } from "vitest";
import type { RaidItem } from "./api-raid";
import { raidHtml, raidMarkdown } from "./raid-copy";

const item = (over: Partial<RaidItem> = {}): RaidItem => ({
  item_id: 1, raid_id: "K8S-R-001", workstream: "K8S", type: "risk",
  title: "Main PR for #6395 may miss Code Freeze",
  quote: "Synthetic: the main PR for #6395 still needs an approver from SIG Storage.",
  source: { kind: "meeting", title: "Release team notes", url: "https://docs.example/notes", date: "2026-11-10T17:00:00Z", synthetic: false },
  owner: "SIG Storage", status: "open", review: "confirmed", links: [], merge_suggestion: null,
  created_at: "2026-11-10T17:00:00Z", updated_at: "2026-11-10T17:00:00Z", ...over,
});

describe("RAID copy", () => {
  it("writes a Markdown table of id, type, title, owner, status and the source link", () => {
    const md = raidMarkdown([item(), item({ raid_id: "K8S-A-001", type: "action", owner: null, status: "closed", source: { kind: "meeting", title: "No link", url: null, date: "2026-11-10T17:00:00Z", synthetic: true } })]);
    expect(md.split("\n")[0]).toBe("| RAID ID | Type | Title | Owner | Status | Source |");
    expect(md).toContain("| K8S-R-001 | risk | Main PR for #6395 may miss Code Freeze | SIG Storage | open | [Release team notes](https://docs.example/notes) |");
    expect(md).toContain("| K8S-A-001 | action | Main PR for #6395 may miss Code Freeze | No owner | closed | No link |");
    expect(md).not.toContain("Synthetic:");
  });

  it("writes an HTML table and escapes the title", () => {
    const html = raidHtml([item({ title: "Risk <script> & quote" })]);
    expect(html.startsWith("<table><thead><tr><th>RAID ID</th>")).toBe(true);
    expect(html).toContain("<td>K8S-R-001</td><td>risk</td><td>Risk &lt;script&gt; &amp; quote</td><td>SIG Storage</td><td>open</td>");
    expect(html).toContain('<a href="https://docs.example/notes">Release team notes</a>');
    expect(html).not.toContain("<script>");
  });
});
