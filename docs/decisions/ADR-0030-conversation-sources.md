# ADR-0030: Conversation sources (meeting notes, meeting transcripts, Slack)

- **Status:** accepted for public Google Doc meeting notes and retros (Waves 4-5: RAID
  extraction on the v1.38 notes and the v1.37 retro, addenda 2-5); proposed for the
  rest. Evidence from official documentation and live public fetches. Live API calls for Slack, Zoom, Microsoft Teams and Google Meet are still owed
  (they need test apps the owner creates). Each section says which.
- **Date:** 2026-11-25

## Context

The RAID tracker (risks, actions, issues, decisions), the risk analyst and the VP update
need what people *say*, not only what they commit: decisions made in a meeting, a risk
raised in a channel. CLAUDE.md §7 requires checking a new source with real API calls
before building on it, and recording what is available, its limits and its terms. §2.7
allows only public or clearly labelled synthetic meeting notes for the public demo.

The owner asked for connectors for Zoom, Microsoft Teams, Google Meet and Slack
(2026-11-25), and chose this order: Slack first (this project's own workspace), then one
meeting source, decided by the evidence below.

## Evidence

### Public meeting notes: Kubernetes release team (live, verified 2026-11-25)

- `kubernetes/sig-release/releases/release-1.38/links.md` links "Google Doc for v1.38
  Release Meeting" (document `1fkUQyLupx_jkPcXtWmxnmVVVMj7KHRizx_yBRxJMOw0`). The same page
  also links a Release Retrospective doc.
- A plain-text export of that document returned **HTTP 200, 84,760 bytes, without signing
  in**. It is the real v1.38 release-team meeting notes: "Everyone can comment;
  release-team@kubernetes.io can edit", meetings every Wednesday, then Monday, Wednesday
  and Friday from 23 November 2026.
- Collect it through the **Google Drive API** (`files.export` of a publicly shared file),
  not by scraping a web page.
- Not yet verified: that `files.export` works with an API key for this document, and the
  licence that applies to Kubernetes community notes. `kubernetes/sig-release` itself is
  Apache-2.0; CC BY 4.0 for community content is not confirmed here.
- Privacy: the notes contain contributor names. Store them for linking, display roles and
  counts only (CLAUDE.md §10).

### Slack (official docs, docs.slack.dev, read 2026-11-25)

- Read-only scopes: `channels:history` ("View messages and other content in public
  channels that your Slack app has been added to"), `groups:history` for private channels,
  plus `channels:read`. A bot only reads channels it is a member of.
- New messages arrive as the `message.channels` event (Events API). Requests are signed:
  `X-Slack-Signature` = `v0=` + HMAC-SHA256(signing secret, `v0:{timestamp}:{raw body}`),
  timestamp within five minutes. Reply 2xx within three seconds. Slack retries three times
  (immediately, after 1 minute, after 5 minutes), and pauses the subscription if more than
  95% of deliveries fail within 60 minutes.
- `conversations.history` (backfill): Tier 3, "50+ per minute", per method per workspace,
  `429` with `Retry-After`.
- Not confirmed by the pages read: any different limit for apps that are not on the Slack
  Marketplace, and free-plan history limits. The live test answers both.

### Zoom (official docs, developers.zoom.us, read 2026-11-25)

- Transcripts come with a meeting's **cloud recording** (`GET /meetings/{id}/recordings`,
  file type `TRANSCRIPT`, VTT), read-only `cloud_recording:read:*` scopes. This part was
  read from a summary of a very long page and is **not verified word for word**.
- Webhooks are signed (`x-zm-signature`, HMAC-SHA256 over `v0:{timestamp}:{body}`) with a
  URL validation handshake re-checked every 72 hours. A `recording.completed` event
  exists. A transcript-specific event was **not found**.
- Rate limits are per account. The recording endpoints are "Light": 4/s and 6,000/day on
  Free, 30/s on Pro, 80/s on Business+.
- Plan requirement (cloud recording and audio transcript enabled): **not confirmed** by
  the pages read. Expected to need a paid plan.

### Microsoft Teams (official docs, learn.microsoft.com, read 2026-11-25)

- `GET /users/{id}/onlineMeetings/{id}/transcripts` and `.../content`. WebVTT with speaker
  tags by default, or a format without speaker attribution. Not for live events, expired
  meetings, or meetings not tied to a calendar event.
- Permission `OnlineMeetingTranscript.Read.All` (delegated or application). Personal
  Microsoft accounts are not supported. Application access also needs a tenant **application
  access policy** (`New-CsApplicationAccessPolicy`), and the tenant admin must enable Graph
  access to transcripts.
- `getAllTranscripts` with delta can sync new transcripts for one organizer (application
  permission only, not channel meetings).
- Not retrieved: change notifications for transcripts, and licensing or metered billing.

### Google Meet (official docs, developers.google.com, read 2026-11-25)

- `conferenceRecords.transcripts.entries` gives one entry per stretch of speech, with
  participant and start and end times. Records and entries are **deleted 30 days after the
  meeting**, so collection must run within that window.
- User authentication only. `meetings.space.readonly` is a *sensitive* scope (app
  verification). Downloading the transcript document needs a *restricted* Drive scope
  (security assessment).
- The Workspace Events API sends `google.workspace.meet.transcript.v2.fileGenerated`
  through Pub/Sub when a transcript is ready.
- Not confirmed: which Workspace editions produce transcripts, and quotas.

## Decision (proposed)

1. **One normalized conversation event for every source.** A segment of a meeting
   transcript or notes document, or one chat message, carrying its source, timestamp,
   verbatim text, speaker *role* (never shown as a name) and a link back. Teams declare
   `provides: conversations` and the channels, documents or meetings to read in their
   connector file. `engine/`, `pipeline/`, `verify/` and `api/` do not change per source.
2. **Order:**
   1. **Public meeting notes**: Kubernetes release-team notes through the Drive API. Real,
      public and allowed today, with no account or paid plan.
   2. **Slack**: this project's own workspace, read-only bot, Events API plus backfill.
   3. **One meeting-transcript source**: the one the owner's organization uses. Zoom needs
      a paid plan with cloud recording. Teams needs an admin policy. Meet needs app
      verification and collection within 30 days.

   The other two follow on the same event format.
3. **AI only suggests.** The RAID extractor returns items with a quote that must match the
   source word for word. Items stay `suggested` until a TPM confirms them. An eval set of
   30+ labelled excerpts gates the extractor in CI.
4. **Read-only, signed, recorded.** Every source uses read-only scopes. Webhooks verify
   their signature. Secrets are kept in Secret Manager. Each collector is traced with
   OpenTelemetry. Only the text needed for RAID is stored, and no audio or video.

## Alternatives

- Synthetic notes only: always available, but they prove nothing about real meetings.
  Kept as a fallback, labelled synthetic.
- Zoom, Teams or Meet first: each needs a paid plan, admin policy or app verification
  before a single real transcript, and their data is private, so not usable for the public
  demo.
- Reading the notes web page directly: rejected, because CLAUDE.md requires APIs, not scraping.

## Still to verify (live calls owed)

- Slack: create the app in this project's workspace, call `conversations.history` and
  receive one signed event. Record the limits actually returned.
- Drive API `files.export` of the v1.38 notes with an API key (the public export works, addendum 2). The notes' licence: not confirmed (addendum 2).
- The chosen meeting tool: one real transcript fetched end to end.

## Addendum (2026-11-25): connectors built ahead of live checks

The owner asked for the Slack, Zoom, Microsoft Teams and Google Meet connectors before the
test accounts exist. They are built against the official documentation above and tested
on synthetic payloads shaped like it. **None has been called against a real service.**
Each runs only for a team that lists it under `conversations` and has its credentials
set, so nothing runs by default. A connector counts as verified only after one real call
end to end, recorded here with the date.

- Slack (`collectors/slack`, `kind: slack_channel`, `SLACK_BOT_TOKEN`): channel history
  and thread replies, people's messages only (no channel notices or bot posts), one
  `chat` segment per message. It polls a window (default 14 days); the Events API webhook
  comes later. **Not live-verified.**

## Addendum 2 (2026-11-25): source check for Wave 4 and 5, and the RAID model

### Source check (#175)

Fetched with `collectors/notes/client.py` as it is. No `GOOGLE_API_KEY` is set, so every
fetch used the **public plain-text export** (`/document/d/{id}/export?format=txt`), not the
Drive API. Each call returned HTTP 200 with the document text.

| Document | ID | Fetched (UTC) | Size | Content |
|---|---|---|---|---|
| Kubernetes v1.38 Release Team meeting notes | `1fkUQyLupx_jkPcXtWmxnmVVVMj7KHRizx_yBRxJMOw0` | 2026-11-25 20:53 | 85,338 characters, 1,925 lines | 12 dated meetings from Week 1 (2 Sep 2026) to Week 13 (25 Nov 2026), weekly and burndown |
| Kubernetes v1.37 Release Retrospective | `1mMMDAfuEgYqxJZ-3ZmllBPlD5-niZF6-16T8yF6uMxE` | 2026-11-25 20:53 | 21,949 characters, 222 lines | One retro, linked from `kubernetes/sig-release/releases/release-1.37/links.md` |
| Kubernetes v1.36 Release Retrospective (fallback) | `11C7O8cgDxhjUJ-FcuOYwn_-tjcFva3SwADCFEUPN3NI` | 2026-11-25 20:53 | 30,662 characters, 446 lines | One retro |

**Decision: real sources.** The v1.38 notes and the v1.37 retro are fetchable, non-empty and
public, so both are used. The v1.36 retro stays the fallback, and no synthetic notes are
needed. Fixture endpoints (#174) remain labelled synthetic until the store is wired in.

**Licence: not confirmed.** `kubernetes/community` and `kubernetes/sig-release` are both
Apache-2.0 (GitHub licence API, `LICENSE` at each root, checked 2026-11-25). The documents
themselves are Google Docs outside those repositories and carry no licence or reuse notice
(searched the fetched text for "licen", "copyright", "creative"). So the platform stores only
the text it needs for each RAID item (its verbatim quote and the meeting date), links every
item to the source document, and never republishes a whole document.

**Privacy.** The notes attribute lines to people (`[Name] …`: 46 tags in the v1.38 notes, 84
in the v1.37 retro, 93 in the v1.36 retro) and include meeting links and passcodes.
- A leading speaker tag is attribution, not part of the quote. The quote check runs on the
  line after the tag.
- A quote is stored verbatim for verification. Any `[Name]` left inside it is masked as
  `[participant]` whenever it is returned by the API or sent to an AI model.
- Owners are roles or teams ("Release lead", "SIG Node"), never names. Passcodes and meeting
  links are never stored.

### RAID model

**Fields.** `item_id` (internal, stable), `raid_id`, `workstream`, `type` (risk, action,
issue, decision, question), `title`, `quote` (verbatim), source (kind, document ID, meeting
date, URL), `owner` (role or team), `status`, `review`, links (method and status), an
optional merge suggestion with its reason, and timestamps. Contract:
`docs/api/raid-contract.md`.

**ID rule.** `{WORKSTREAM}-{TYPE}-{SEQ}`: workstream from the team's connector (`K8S`,
`KAFKA`, `PIP`), type letter R, A, I, D or Q, and a three-digit sequence per workstream and
type. The ID is given on the first confirm or edit, never changed, never reused (a rejected
or superseded item keeps its number used), and never given to a rejected item. Suggested
items have no RAID ID.

**Identity of a suggestion.** Hash of (source document, meeting date, type, normalized
quote). Re-running the extractor on the same notes finds the same suggestion and adds
nothing, so a replay is idempotent. A rejected suggestion is never suggested again.

**Lifecycle.** `status`: open → in_progress → closed or superseded. `review`: suggested →
confirmed, edited or rejected. Every change appends a history row (who as a role, when,
what changed, reason). Rows are never updated or deleted.

**Merge rules.** The platform only suggests a merge, with a stored reason, when two items
have the same type and release and either share an explicit key (a KEP or issue number) or
have quotes whose word overlap is at least 0.6 (Jaccard on lowercased word sets). A person
accepts it by superseding one item, which keeps its ID and history.

**Links.** An explicit KEP or issue number in the quote links through the linker as
`explicit_key` and is verified. Anything else the model proposes stays `ai_suggested` until a
person confirms it.

**Eval threshold (the CI gate, #178).**
- Quote match: **100%** of kept items must match their source word for word (whitespace
  differences only). Any miss fails the gate.
- Precision ≥ **0.80** and recall ≥ **0.60** for each type with at least 5 labelled items in
  `evals/cases/raid/`. Types with fewer are reported but do not gate.
- Every run reports real numbers, failures included.

## Addendum 3 (2026-11-25): RAID extractor, eval and the v1.38 run (#177–#179)

**Masking is applied before storage, not only on output** (stricter than addendum 2). The
extractor sees only masked text, and the quote is checked against that text, so the stored
quote is the source's words with names, handles and speaker tags replaced by
`[participant]`. Names come from the notes themselves: attendee and host lines, team
headings ("Docs (Name / @handle)"), leading speaker tags, their first names and short forms
of those first names ("Fred" for "Frederico"). Roster lines are removed before extraction.
Email addresses of organisations (`pr@cncf.io`) are kept. Owners are the team headings found
in the notes (Enhancements, Release Signal, Docs, Comms, Release Branch Management,
Subproject Leads, Release Lead), never people.

**Known gap.** A person named in passing who is on no roster in the notes is not masked: in
the v1.38 run, one first name in 2 of 126 kept items. The fix is a second name source (the
public release-team roster in `kubernetes/sig-release`). It is owed before RAID items are
served publicly (#180).

**Eval (#178), 5 builder-written seed cases** (masked excerpts of five v1.38 meetings, 35
expected items). Every run is in `docs/results/` or summarised here:

| Run (UTC) | Prompt | Model | Quote match | Action P / R | Issue P / R | Gate | Cost |
|---|---|---|---|---|---|---|---|
| 2026-11-25 22:56 | v1 | claude-haiku-5-5 | 100% | 0.789 / 0.833 | 0.778 / 0.700 | **fail** | $0.006 |
| 2026-11-25 22:57 | v2 | claude-haiku-5-5 | 100% | 0.895 / 0.944 | 0.769 / 1.000 | **fail** (issue precision) | $0.006 |
| 2026-11-25 22:58 | v2 | claude-sonnet-5-5 | 100% | 0.938 / 0.833 | 0.692 / 0.900 | **fail** (issue precision) | $0.057 |

Risk (4 labels), decision (4) and question (0) are below the 5-label minimum and do not
gate. v2's rules were written after reading v1's errors on these same seeds, so its numbers
are optimistic. Most remaining issue "false positives" are type disagreements (the model
calls a missing docs PR an issue; the label calls it a risk) or one flaky test listed on its
own where the label grouped three. The labels were not changed after seeing the outputs.
The stronger model did not help and costs ten times more, so the cheaper one stays. The real
measure is Cursor's independent cases in `evals/cases/raid/`, which the gate picks up.

**The gate reports before it blocks** (owner's decision, 2026-11-25). CI runs it and prints
the real numbers on every run, marked failing while they are under the threshold. It blocks
merges only once `evals/cases/raid/` holds at least 30 cases not marked `seed`
(`MIN_INDEPENDENT` in `evals/raid_extractor.py`). Until then a builder-tuned score on five
seeds would decide nothing useful either way, and no extracted item is shown or used before
a person confirms it.

**v1.38 run (#179)**, prompt v2 on claude-haiku-5-5, over the 13 stored meetings (2 Sep to
25 Nov 2026, read from the shared core after `make notes-sync`):

| Meetings | Returned | Dropped (quote under 4 words) | Dropped (quote not found) | Kept | Action | Issue | Risk | Decision | Question | With team owner | With explicit link | Possible repeats | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 13 | 132 | 6 | 0 | 126 | 59 | 37 | 14 | 14 | 2 | 121 | 5 | 23 | $0.016 (first run; re-runs are cache hits) |

All 126 are `suggested`. None has a RAID ID until a person confirms it. The run above kept
items in memory (`--dry-run`) because the RAID tables (migration 0010, #176) are not merged
yet. Re-running without `--dry-run` after that merge puts the same items in the queue at no
AI cost.

## Addendum 4 (2026-11-25): a second name source for masking (#180)

Masking from the notes alone missed people named in passing who are on no attendee list
(addendum 3: one first name in 2 of 126 v1.38 items). A team's config can now list
`people_sources`: public GitHub files that list its people as `Name ([@handle](...))`. For
Kubernetes these are the v1.38 and v1.37 `release-team.md` files in `kubernetes/sig-release`
and `release-managers.md` in `kubernetes/website`, 113 names and handles in total
(2026-11-25).

- **Read when masking runs, never stored.** `collectors/notes/people.py` reads them through
  the GitHub contents API (read-only, the shared HTTP client) each time the RAID job runs.
  Names exist only in memory, to be replaced by `[participant]` before any text reaches the
  model or the store. Storing them as events would keep a list of people in the database for
  no other use, so this is the one place a job reads a source directly; it reads no content
  that ends up stored.
- **A list that cannot be read is skipped with a warning**, and masking falls back to the
  names in the notes.
- **Measured** on the v1.38 run (prompt v2, claude-haiku-5-5, 2026-11-25): no listed or
  rostered name in any kept quote or title, and a scan of capitalised words in all 128 kept
  items found only weekdays, months, products and Kubernetes terms. Counts after the change:
  136 returned, 8 dropped (7 too short, 1 quote not found), 128 kept (58 actions, 37 issues,
  16 risks, 15 decisions, 2 questions), 125 with a team owner, 5 with explicit links, 22
  possible repeats. Re-run cost $0.004 (9 of 13 meetings were cache hits).

## Addendum 5: more people sources and surnames (#183, 2026-11-26)

The v1.37 retrospective named a SIG lead who is on no release-team list. The people
sources now include kubernetes/community `sigs.yaml` (`- github:` / `name:` pairs, read
the same way, never stored). Masking now also covers a listed person's surname used on
its own, after a v1.38 item kept one. Re-checked against 619 public names: 0 names left
in the v1.38 or v1.37 items (ADR-0032 addendum 3).
