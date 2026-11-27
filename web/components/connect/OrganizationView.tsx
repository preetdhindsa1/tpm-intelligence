import type { ReactNode } from "react";
import Link from "next/link";
import { SPEND_UNMEASURED, connectorLine, createLine, ownerOnly, secretLine, type ConnectorRow, type OrgList, type OrgRef } from "@/lib/org";
import type { Loaded } from "@/lib/org-load";

export type Limits = { ai_daily_budget_usd: number; max_teams: number; teams: number };
export type Connector = ConnectorRow;
export type Member = { login: string; role: string };
export type Audit = { id: number; at: string; actor: string; action: string; target: string };

export function OrganizationView({
  login,
  list,
  org,
  limits,
  connectors,
  members,
  audit,
}: {
  login: string | null;
  list: Loaded<OrgList> | null;
  org: OrgRef | null;
  limits: Loaded<Limits> | null;
  connectors: Loaded<{ connectors: Connector[] }> | null;
  members: Loaded<{ members: Member[] }> | null;
  audit: Loaded<{ entries: Audit[] }> | null;
}) {
  if (!login) {
    return <p className="text-slate-600">Sign in to see your organizations.</p>;
  }
  if (!list || !list.ok) {
    return <p className="text-slate-600">{list?.detail ?? "Organizations could not be loaded."}</p>;
  }
  return (
    <div className="space-y-6">
      <p className="text-slate-600">{createLine(list.data.can_create)}</p>
      {list.data.tenants.length === 0 ? <p>You are not a member of an organization.</p> : null}
      <ul className="flex flex-wrap gap-2">
        {list.data.tenants.map((t) => (
          <li key={t.id}>
            <Link href={`/connect/organization?org=${encodeURIComponent(t.id)}`} className={t.id === org?.id ? "font-semibold text-slate-900" : "text-slate-600"}>
              {t.name} · {t.role}
            </Link>
          </li>
        ))}
      </ul>
      {org ? <OrgDetail org={org} limits={limits} connectors={connectors} members={members} audit={audit} /> : null}
    </div>
  );
}

function OrgDetail({
  org,
  limits,
  connectors,
  members,
  audit,
}: {
  org: OrgRef;
  limits: Loaded<Limits> | null;
  connectors: Loaded<{ connectors: Connector[] }> | null;
  members: Loaded<{ members: Member[] }> | null;
  audit: Loaded<{ entries: Audit[] }> | null;
}) {
  return (
    <section className="space-y-4">
      <h2 className="font-heading text-2xl font-bold">{org.name}</h2>
      {org.public ? <p className="text-slate-600">The public demo is changed in the repository, not here.</p> : null}
      <Block title="Limits" loaded={limits}>
        {limits?.ok ? (
          <p>
            AI budget ${limits.data.ai_daily_budget_usd} a day. Teams {limits.data.teams} of {limits.data.max_teams}. {SPEND_UNMEASURED}
          </p>
        ) : null}
      </Block>
      <Block title="Connectors" loaded={connectors}>
        {connectors?.ok ? (
          <ul className="space-y-2">
            {connectors.data.connectors.map((c) => (
              <li key={c.team_id}>
                {connectorLine(c)}
                <ul>
                  {(c.secrets ?? []).map((s) => {
                    const line = secretLine(s);
                    return line ? <li key={line.ref}>{line.ref}: {line.found ? "found" : "missing"}</li> : null;
                  })}
                </ul>
              </li>
            ))}
            {connectors.data.connectors.length === 0 ? <li>No connectors.</li> : null}
          </ul>
        ) : null}
      </Block>
      {ownerOnly(org) ? (
        <>
          <Block title="Members" loaded={members}>
            {members?.ok ? (
              <ul>
                {members.data.members.map((m) => (
                  <li key={m.login}>{m.login} · {m.role}</li>
                ))}
              </ul>
            ) : null}
          </Block>
          <Block title="Audit" loaded={audit}>
            {audit?.ok ? (
              <ul>
                {audit.data.entries.map((row) => (
                  <li key={row.id}>{row.actor} · {row.action} · {row.target}</li>
                ))}
                {audit.data.entries.length === 0 ? <li>No audit records.</li> : null}
              </ul>
            ) : null}
          </Block>
        </>
      ) : null}
    </section>
  );
}

function Block({ title, loaded, children }: { title: string; loaded: { ok: boolean; detail?: string } | null; children: ReactNode }) {
  return (
    <div>
      <h3 className="font-semibold">{title}</h3>
      {loaded && !loaded.ok ? <p className="text-slate-600">{loaded.detail}</p> : children}
    </div>
  );
}
