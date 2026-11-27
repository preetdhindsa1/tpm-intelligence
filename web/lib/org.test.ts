import { describe, expect, it } from "vitest";
import { CREATE_CLOSED, connectorLine, createLine, ownerOnly, secretLine, selectedOrg, type OrgList } from "./org";

const list: OrgList = {
  tenants: [
    { id: "demo", name: "Public demo", role: "reader", public: true },
    { id: "acme", name: "Acme", role: "owner", public: false },
  ],
  can_create: false,
};

describe("organizations", () => {
  it("says creation is closed unless the API allows it", () => {
    expect(createLine(false)).toBe(CREATE_CLOSED);
    expect(createLine(true)).toBe("You can create an organization.");
  });

  it("selects only an organization the API listed", () => {
    expect(selectedOrg(list, "acme")?.name).toBe("Acme");
    expect(selectedOrg(list, "other")).toBeNull();
    expect(selectedOrg(list, undefined)?.id).toBe("acme");
  });

  it("shows member management only to an owner of a private organization", () => {
    expect(ownerOnly(list.tenants[1])).toBe(true);
    expect(ownerOnly(list.tenants[0])).toBe(false);
    expect(ownerOnly({ id: "acme", name: "Acme", role: "reader", public: false })).toBe(false);
  });

  it("keeps a secret reference and drops anything that is not found or missing", () => {
    expect(secretLine({ ref: "github-token", found: true })).toEqual({ ref: "github-token", found: true });
    expect(secretLine({ ref: "github-token", found: false })).toEqual({ ref: "github-token", found: false });
    expect(secretLine({})).toBeNull();
  });

  it("labels a connector from the team id, display name, and planning source", () => {
    expect(connectorLine({
      team_id: "acme-web",
      config: { display_name: "Acme web", planning: { source: "github" } },
    })).toBe("acme-web · Acme web · github");
    expect(connectorLine({ team_id: "acme-web", config: { display_name: "acme-web" } })).toBe("acme-web");
  });
});
