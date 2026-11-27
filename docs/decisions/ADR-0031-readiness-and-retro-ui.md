# ADR-0031: Readiness and retro UI

- **Status:** accepted
- **Date:** 2026-11-26

## Context

Wave 5 shows a go/no-go and a retro from facts ADR-0032 already computes. The
readiness backtest failed
([docs/results/readiness-backtest-20261126T171219Z.json](../results/readiness-backtest-20261126T171219Z.json):
false no-go 0.119 against the 0.05 limit), so the page must say "not validated"
(principle 5).
Said versus showed puts meeting items next to that day's snapshot. The snapshot
counts are for the whole release, not for one risk, so the page must not claim a
risk was raised before, after, or never against the platform. Both screens are
Live Cockpit sections of one release (docs/ux/ux-v1-locked.md addendum).

## Decision

### Readiness

`/projects/{project}/releases/{name}/readiness` renders `GET /readiness`. The
verdict is the API's word: Ready, Not ready, or Unknown. A synthetic body shows
"Synthetic data". `validated: false` shows "Not validated" and the API's
`validation_note`. An AI summary is shown only when `summary` is a non-empty list.
Each criterion shows the API status (Pass, Fail, Unknown) and its detail. Unknown
adds the exact line "no data to decide". Evidence is a link only when the API sent
a URL. The go / no-go / defer form is visible only to an approver, and the note
must be at least 3 characters. The decision log is newest first. An empty log says
"No decision yet." A failed load is the shared error state and no stand-in verdict.

On the lifecycle bar, the front-page stages and the portfolio stage bar, Launch
links to this page when `coming_next` marks readiness `live`. The stage says "Live"
only when that entry's `validated` is `true`. `false`, `null`, or a missing field
says "Live · not validated".

### Retro

`/projects/{project}/releases/{name}/retro` renders `GET /retro`. A 404 shows the
exact sentence "Retro not computed yet for this release". Any other failure is the
shared error state. The heading is the API `label`. A synthetic body shows
"Synthetic data". Totals use the API numbers. "Planned" and "Warned and landed"
appear only when the API sent a number. Slips say Dropped, Moved to {release}, or
Late exception. A slip with no `first_warning_at` says "no warning before the slip".
No slips says "No slips."

Patterns come from `GET /retro/patterns`. A failed call says "Patterns are not
available" and the rest of the page stays. An empty pattern list says "No pattern
is large enough to show." `suppressed_groups` above zero says "N groups too small
to show" (or "1 group too small to show").

**Said versus showed** is a section on the same page, from
`GET /retro/said-vs-showed`. Meetings are oldest first. Each row is two columns:
Said (type, a Suggested badge when `review` is `suggested`, and the quote only when
the item has one) and Showed (the day's release-wide facts). A null fact says
"not measured". Empty said says "Nothing said." Empty showed says "Nothing shown."
No rows says "No meetings to compare." A failed call says "Said versus showed is
not available" and does not hide the retro. The page does not label a risk as
raised before the platform, after it, or never shown.

Learn, on the same three stage surfaces as Launch, links here only when that
program's `has_retro` is `true`. Otherwise the stage says "No data yet" and does
not link. A global retro `live` flag and the release date are not treated as a
stored retro.

## Alternatives considered

- A before/after/never line on each said item. Rejected. Showed is a release-wide
  count, so that line would be a comparison the API does not support (principles 1
  and 5).
- Hiding readiness until the backtest passes. Rejected. The criteria are still
  facts. The page shows them and says "Not validated".
- Treating a missing retro total as zero. Rejected. Optional totals stay off the
  page until the API sends a number.
- Linking Learn for every program once any retro exists, or once the release date
  has passed. Rejected. `has_retro` is the per-program fact.
- A top-level Readiness or Retro item in the app menu. Rejected. Both belong to
  one release.

## Trade-offs and consequences

Someone can read an unvalidated go/no-go as a decision. The badge and the
validation note stay on the page for that reason, and only an approver can record
a call. Said versus showed will not say whether the platform warned about a
particular risk until the API links a said item to a feature and a first warning
day. Revisit the layout then. Do not invent that link in the web.

## AI vs rules

A readiness summary, when the API sends one, is the only AI text on these pages,
and it is shown as sent. Verdicts, criteria, slips, totals, pattern counts and
showed facts are the API's. This UI does not compute them and does not turn a
missing value into a zero or a verdict.
