# ADR-0029: RAID review UI

- **Status:** accepted
- **Date:** 2026-11-26

## Context

Wave 4 stores RAID items as suggestions until a person confirms them (CLAUDE.md §2 and
§6, ADR-0030). The page has to show the quote, the owner and the source without turning
an AI suggestion into a fact, and without posting anything back to the meeting notes.
The screen is a Live Cockpit section of one release, not a new top-level item
(docs/ux/ux-v1-locked.md addendum).

## Decision

`/projects/{project}/releases/{name}/raid` has two tabs.

**Waiting for review** lists `review: suggested` items only. One card is current.
`j` and `k` move, `c` confirms, `e` edits, `r` rejects. Those keys do nothing while
the focus is in a field. Confirm, edit and reject are sent only when the signed-in
user is an approver; everyone else sees the queue and a note that the page is
read-only. The quote is shown and is not an input. An edit may change title, type,
owner or status. The owner is a role, or the words "No owner". A link line names the
method and status (`explicit key` or `AI suggested`). There is no confidence number.
A merge suggestion is a sentence ("Might repeat item …") and is not applied. Reject
requires a reason of at least 3 characters. A rejected item is not given a RAID ID.
Progress is "{reviewed} of {reviewed + still waiting} reviewed", using the summary's
already-decided counts plus decisions made in this visit. An empty queue says
"Nothing is waiting for review." A synthetic list shows "Synthetic data".

**Tracker** lists confirmed and edited items. Suggested and rejected items are left
out of the list and out of the copy. Filters are type, status and workstream, and
copy follows the filter. "Copy as Markdown" and "Copy as HTML" write a table to the
clipboard (RAID ID, type, title, owner, status, source). The page then says "Copied
as {kind}. Nothing was sent." History, loaded when a row is opened, is oldest first.
The actor is `extractor` or `approver`. Any other actor is shown as `approver`, never
as a login. An empty filter says "No confirmed items match these filters."

The Live Cockpit overview shows three counts from `GET /raid/summary` when
`sources` is not zero: open confirmed risks, risks without an owner, and items
waiting for review. Each count links to this page. Zero sources says "No meeting
notes are connected for this release" and shows no zeros. A failed load is the
shared error state and no stand-in rows.

## Alternatives considered

- Editing the quote. Rejected. The quote has to match the source word for word.
- Posting the tracker to the notes document or to Slack. Rejected. Copy stays on
  the clipboard, and a person sends it (principle 4).
- A confidence score on each suggestion. Rejected. The contract has method and
  status, not a number the page would be inventing.
- Auto-merging items the extractor flagged as repeats. Rejected. A merge stays a
  suggestion until a person decides.
- A top-level RAID item in the app menu. Rejected. RAID belongs to one release.

## Trade-offs and consequences

Keyboard actions are easy to hit by mistake, so they are ignored in fields and for
anyone who is not an approver. Copy can include only the filtered confirmed rows, so
a pasted tracker cannot smuggle in suggestions. Revisit this if a second tenant needs
the queue to remember position across visits, or if copy should include the quote.

## AI vs rules

The extractor (ADR-0030) suggests items. This screen does not extract, score, merge
or count. Progress, filters and the clipboard table are deterministic. A person
confirms, edits or rejects.
