import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RaidItem, RaidList } from "@/lib/api-raid";
import { Tracker } from "./Tracker";

const browserGet = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api-http", () => ({ browserGet }));

afterEach(cleanup);

const base: RaidItem = {
  item_id: 1, raid_id: "K8S-R-001", workstream: "K8S", type: "risk",
  title: "Main PR for enhancement #6395 may miss Code Freeze",
  quote: "Synthetic: the main PR for #6395 still needs an approver from SIG Storage.",
  source: { kind: "meeting", title: "notes", url: null, date: "2026-11-10T17:00:00Z", synthetic: true },
  owner: "SIG Storage", status: "open", review: "confirmed", links: [], merge_suggestion: null,
  created_at: "2026-11-10T17:00:00Z", updated_at: "2026-11-12T17:00:00Z",
};
const list: RaidList = {
  project: "kubernetes", release: "v1.38", as_of: "2026-11-25T21:00:00Z", synthetic: true,
  items: [base, { ...base, item_id: 4, raid_id: null, review: "suggested", title: "Still suggested" }],
};

describe("RAID tracker", () => {
  it("hides suggested items and shows history oldest first, with the actor as a role", async () => {
    browserGet.mockResolvedValue({
      item_id: 1, raid_id: "K8S-R-001", synthetic: true,
      history: [
        { at: "2026-11-10T18:00:00Z", actor: "octocat", action: "confirmed", changes: {}, reason: null },
        { at: "2026-11-10T17:00:00Z", actor: "extractor", action: "suggested", changes: {}, reason: null },
      ],
    });
    render(<Tracker list={list} />);
    expect(screen.queryByText("Still suggested")).toBeNull();
    expect(screen.queryByText(base.quote)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /K8S-R-001/ }));
    const text = (await screen.findByText(/extractor · suggested/)).parentElement?.textContent ?? "";
    expect(text.indexOf("extractor · suggested")).toBeLessThan(text.indexOf("approver · confirmed"));
    expect(text).not.toContain("octocat");
    expect(screen.getByText(base.quote).tagName).toBe("BLOCKQUOTE");
  });
});
