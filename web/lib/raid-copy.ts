// Clipboard text for the filtered tracker. Nothing here is sent or posted.
import type { RaidItem } from "@/lib/api-raid";
import { ownerText } from "@/lib/raid-review";

const COLS = ["RAID ID", "Type", "Title", "Owner", "Status", "Source"] as const;

function plain(value: string): string {
  return value.replace(/\|/g, "\\|").replace(/\n/g, " ");
}

function sourceText(item: RaidItem): string {
  return item.source.url ? `${item.source.title} (${item.source.url})` : item.source.title;
}

/** A Markdown table of the rows the tracker is showing. */
export function raidMarkdown(items: RaidItem[]): string {
  const head = `| ${COLS.join(" | ")} |`;
  const rule = `| ${COLS.map(() => "---").join(" | ")} |`;
  const body = items.map((item) => {
    const source = item.source.url ? `[${plain(item.source.title)}](${item.source.url})` : plain(item.source.title);
    const cells = [item.raid_id ?? "", item.type, plain(item.title), plain(ownerText(item.owner)), item.status, source];
    return `| ${cells.join(" | ")} |`;
  });
  return [head, rule, ...body].join("\n");
}

function html(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** An HTML table of the same rows. A source with a URL is a link. */
export function raidHtml(items: RaidItem[]): string {
  const head = COLS.map((c) => `<th>${c}</th>`).join("");
  const body = items.map((item) => {
    const source = item.source.url
      ? `<a href="${html(item.source.url)}">${html(item.source.title)}</a>`
      : html(sourceText(item));
    const cells = [item.raid_id ?? "", item.type, item.title, ownerText(item.owner), item.status].map((c) => `<td>${html(c)}</td>`);
    return `<tr>${cells.join("")}<td>${source}</td></tr>`;
  });
  return `<table><thead><tr>${head}</tr></thead><tbody>${body.join("")}</tbody></table>`;
}
