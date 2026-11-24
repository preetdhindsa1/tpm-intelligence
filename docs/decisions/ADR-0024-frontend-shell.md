# ADR-0024: Front end shell, navigation, color, and stage

- **Status:** accepted
- **Date:** 2026-11-24

## Context

UX v1 replaces the old menu with five screens and a lifecycle stage. Release URLs from ADR-0014 stay. A sign-in button on every page tripped Chrome's phishing check (2026-11-23).

## Decision

- Tailwind tokens: ink `#0B1020`, canvas `#F6F7F9`, action `#4F46E5`, healthy `#166534` / `#DCFCE7`, warning `#B45309` / `#FEF3C7`, critical `#B91C1C` / `#FEE2E2`. Space Grotesk for headings, Inter for body, both self-hosted.
- `/` shows Sign in only when GitHub or local dev login is configured, plus **Open the live demo**. Other screens show Search, Live, and the signed-in person. No sign-in button on app screens.
- Live Cockpit and Decision Studio use the program in the URL, then `localStorage` key `pi.lastProgram`, then `/releases`.
- AI-native PDLC links to `/lab` until `/pdlc` exists. ⌘K lists the five screens and the open release's sections. No search API.
- Stage uses the release dates against that release's `as_of`, in UTC. No dates → "Dates not known". Before the first freeze → Plan. Enhancements freeze until Code Freeze → Build. Code Freeze until release → Freeze. The UTC day of `release_at` → Launch. After that day → Learn.

## Alternatives considered

A sign-in button on every screen (phishing flag). Hard-coding Kubernetes v1.38 as the default program. Calling the summary API from the shell to name a stage.

## Trade-offs and consequences

Launch is one UTC day because the API stores a timestamp, not a launch window. Revisit when readiness defines Launch. The PDLC link moves to `/pdlc` when that page ships.

## AI vs rules

No AI. Stage, links, and the last program are deterministic.
