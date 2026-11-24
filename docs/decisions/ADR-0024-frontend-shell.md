# ADR-0024: Front end shell, navigation, color, and stage

- **Status:** accepted
- **Date:** 2026-11-24

## Context

UX v1 replaces the old menu with five screens and a lifecycle stage. Release URLs from ADR-0014 stay. A sign-in button on every page tripped Chrome's phishing check (2026-11-23).

## Decision

- Tailwind tokens: ink `#0B1020`, canvas `#F6F7F9`, action `#4F46E5`, healthy `#166534` / `#DCFCE7`, warning `#B45309` / `#FEF3C7`, critical `#B91C1C` / `#FEE2E2`. Space Grotesk for headings, Inter for body, both self-hosted.
- `/` shows Sign in only when GitHub or local dev login is configured, plus **Open the live demo**. Other screens show Search and the signed-in avatar (initials, with the login in the accessible name, plus Sign out). No sign-in button on app screens. The Live label is the release page's stream state, not a dot on every screen.
- Live Cockpit and Decision Studio use the program in the URL, then `localStorage` key `pi.lastProgram`, then `/releases`.
- AI-native PDLC links to `/lab` until `/pdlc` exists. ⌘K lists the five screens and the open release's sections. No search API.
- Stage uses the same UTC boundaries as ADR-0025, compared to the release's `as_of`. Missing cycle start, Code Freeze, or release → "Dates not known". Before cycle start → Plan. Cycle start until Code Freeze → Build. Code Freeze until release → Freeze. Release until seven days later → Launch. After that → Learn.

## Alternatives considered

A sign-in button on every screen (phishing flag). Hard-coding Kubernetes v1.38 as the default program. Calling the summary API from the shell to name a stage.

## Trade-offs and consequences

Launch is seven days, matching ADR-0025, because the API stores a release timestamp and not a separate launch window. The PDLC link moves to `/pdlc` when that page ships. Portfolio and Connect stay in the menu; their pages are the following issues.

## AI vs rules

No AI. Stage, links, and the last program are deterministic.
