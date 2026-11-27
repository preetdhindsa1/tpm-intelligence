import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CREATE_CLOSED, SPEND_UNMEASURED } from "@/lib/org";
import { OrganizationView } from "./OrganizationView";

afterEach(cleanup);

const acme = { id: "acme", name: "Acme", role: "owner", public: false };
const demo = { id: "demo", name: "Public demo", role: "reader", public: true };

describe("organization settings", () => {
  it("asks a visitor to sign in", () => {
    render(<OrganizationView login={null} list={null} org={null} limits={null} connectors={null} members={null} audit={null} />);
    expect(screen.getByText("Sign in to see your organizations.")).toBeTruthy();
  });

  it("reads limits, connectors, members and audit, and offers no changes", () => {
    render(
      <OrganizationView
        login="octocat"
        list={{ ok: true, data: { tenants: [demo, acme], can_create: false } }}
        org={acme}
        limits={{ ok: true, data: { ai_daily_budget_usd: 0.5, max_teams: 3, teams: 1 } }}
        connectors={{
          ok: true,
          data: {
            connectors: [{
              team_id: "acme-web",
              config: { display_name: "Acme web", planning: { source: "github" } },
              secrets: [{ ref: "github-token", found: true }],
            }],
          },
        }}
        members={{ ok: true, data: { members: [{ login: "octocat", role: "owner" }] } }}
        audit={{
          ok: true,
          data: { entries: [{ id: 41, at: "2026-11-27T10:05:00Z", actor: "owner", action: "connector_changed", target: "acme-web" }] },
        }}
      />,
    );
    expect(screen.getByText(CREATE_CLOSED)).toBeTruthy();
    expect(screen.getByText(/AI budget \$0\.5 a day/)).toBeTruthy();
    expect(screen.getByText(new RegExp(SPEND_UNMEASURED))).toBeTruthy();
    expect(screen.getByText("acme-web · Acme web · github")).toBeTruthy();
    expect(screen.getByText("github-token: found")).toBeTruthy();
    expect(screen.getByText("octocat · owner")).toBeTruthy();
    expect(screen.getByText("owner · connector_changed · acme-web")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("hides member logins and the audit log on the public demo", () => {
    render(
      <OrganizationView
        login="octocat"
        list={{ ok: true, data: { tenants: [demo], can_create: false } }}
        org={demo}
        limits={{ ok: true, data: { ai_daily_budget_usd: 2, max_teams: 20, teams: 3 } }}
        connectors={{ ok: true, data: { connectors: [] } }}
        members={{ ok: true, data: { members: [{ login: "hidden", role: "owner" }] } }}
        audit={{ ok: true, data: { entries: [{ id: 1, at: "t", actor: "owner", action: "x", target: "y" }] } }}
      />,
    );
    expect(screen.getByText("The public demo is changed in the repository, not here.")).toBeTruthy();
    expect(screen.queryByText("hidden · owner")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Members" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Audit" })).toBeNull();
    expect(screen.getByText("No connectors.")).toBeTruthy();
  });
});
