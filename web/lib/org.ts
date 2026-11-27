// Display rules for GET /me/tenants and the tenant admin routes. No numbers are created here.

export type OrgRef = { id: string; name: string; role: string; public: boolean };

export type OrgList = { tenants: OrgRef[]; can_create: boolean };

export const CREATE_CLOSED = "Creating an organization is not open yet.";
export const SPEND_UNMEASURED = "Today's AI spend is not on this route.";

export function createLine(canCreate: boolean): string {
  return canCreate ? "You can create an organization." : CREATE_CLOSED;
}

/** The org in the URL, when it is one the API listed. */
export function selectedOrg(list: OrgList, id: string | undefined): OrgRef | null {
  if (!id) return list.tenants.find((t) => !t.public) ?? list.tenants[0] ?? null;
  return list.tenants.find((t) => t.id === id) ?? null;
}

export function ownerOnly(org: OrgRef): boolean {
  return org.role === "owner" && !org.public;
}

export type SecretRef = { ref: string; found: boolean };

/** A secret line is a name and whether it resolves. Values are never shown. */
export function secretLine(row: { ref?: string; found?: boolean }): SecretRef | null {
  if (!row.ref) return null;
  return { ref: row.ref, found: row.found === true };
}

export type ConnectorRow = {
  team_id: string;
  config?: { display_name?: string; planning?: { source?: string } };
  secrets?: { ref?: string; found?: boolean }[];
};

/** Team id, display name, and planning source from one GET /tenants/{id}/connectors row. */
export function connectorLine(row: ConnectorRow): string {
  const name = row.config?.display_name?.trim() ?? "";
  const source = row.config?.planning?.source?.trim() ?? "";
  return [row.team_id, name && name !== row.team_id ? name : "", source].filter((part) => part !== "").join(" · ");
}
