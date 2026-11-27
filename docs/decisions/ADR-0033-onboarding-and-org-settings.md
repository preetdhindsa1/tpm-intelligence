# ADR-0033: Organization settings, first screen

**Status:** Accepted
**Date:** 2026-11-26

## Context

Wave 6 already serves the tenant routes (`docs/api/tenants-contract.md`, ADR-0034, ADR-0035). Connect your tools still tells the story of a signup that is not open. A screen that invents organizations, spend, or secret values would break the honesty rules.

## Decision

`/connect/organization` is a read of `GET /me/tenants` and, for one organization the API listed, its limits and connectors. Member logins and the audit log are requested only when the signed-in role is `owner` and the organization is not the public demo.

A request for the public demo keeps the version 1 signature. A request for any other organization uses signature version 2 and sends `X-TPM-Tenant` (ADR-0034). The version 1 test vector is unchanged.

The screen says creating an organization is not open when `can_create` is false. It does not offer create, member changes, limit changes, export, or deletion. Secret values are not rendered; a connector secret is a reference and found or missing. Today's AI spend is stated as not on this route.

The page lives under Connect your tools. The top navigation stays the five locked items.

## Alternatives

- A new top-level item. Rejected: the locked navigation does not add one.
- Calling private-tenant routes with the version 1 signature. Rejected: the API accepts version 1 only for `demo`.

## Trade-offs

Owners cannot change an organization from this screen yet. That is the next slice, against the same contract, after this read path is reviewed.
