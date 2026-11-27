import { OrganizationView } from "@/components/connect/OrganizationView";
import type { Audit, Connector, Limits, Member } from "@/components/connect/OrganizationView";
import { loadOrgList, loadTenant } from "@/lib/org-load";
import { ownerOnly, selectedOrg } from "@/lib/org";

export const dynamic = "force-dynamic";

export default async function OrganizationPage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const { org: raw } = await searchParams;
  const { login, list } = await loadOrgList();
  const org = login && list?.ok ? selectedOrg(list.data, raw) : null;
  const [limits, connectors, members, audit] = org && login
    ? await Promise.all([
        loadTenant<Limits>(login, `/tenants/${org.id}/limits`, org.id),
        loadTenant<{ connectors: Connector[] }>(login, `/tenants/${org.id}/connectors`, org.id),
        ownerOnly(org) ? loadTenant<{ members: Member[] }>(login, `/tenants/${org.id}/members`, org.id) : Promise.resolve(null),
        ownerOnly(org) ? loadTenant<{ entries: Audit[] }>(login, `/tenants/${org.id}/audit`, org.id) : Promise.resolve(null),
      ])
    : [null, null, null, null];

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 py-4">
      <header>
        <h1 className="font-heading text-4xl font-bold tracking-tight">Your organizations</h1>
        <p className="mt-2 text-slate-600">What the tenant API returns for the signed-in user. Nothing here is sent back to a source system.</p>
      </header>
      <OrganizationView login={login} list={list} org={org} limits={limits} connectors={connectors} members={members} audit={audit} />
    </div>
  );
}
