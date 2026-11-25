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

Launch is seven days, matching ADR-0025, because the API stores a release timestamp and not a separate launch window. The PDLC link moves to `/pdlc` when that page ships. Portfolio and Connect stay in the menu; their pages are the following issues. The time machine is only on Kubernetes v1.38, because that is the release #6395 belongs to. Other releases do not get a stand-in story.

## Portfolio page

`/portfolio` renders `GET /portfolio` in the order the API returns. `stage.current` null is shown as "Stage unknown". A `coming_next` status of `planned` is shown as "Planned", with no counts added. If the endpoint is not deployed, the page shows the HTTP error and no example numbers.

## AI vs rules

No AI. Stage, links, and the last program are deterministic. The Live Cockpit time machine replays feature #6395's real timeline events from the API, including both freezes and each distinct pull-request event. Identical events at the same timestamp are shown once. The future release date is not shown as an event. It does not rebuild the page's tiles as of that date. The locked spec's "8 real dates" is not a cap on that list.

## Front page

The headline and tagline are the locked words. Live program cards come from `GET /portfolio`. The three stories are omitted when their source is missing: the Kubernetes release summary for removals at Code Freeze (and how many were added back, when the summary says so), and `lib/measured.ts` for Kafka linking and the fact checker. Approving-review counts stay off this page until cross-reviews are counted, because every pull request and review is posted from one account (issue #94). The recorded demo lists five chapters and a 2:00 running time, and says no recording is published.
