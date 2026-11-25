# ADR-0030: Conversation sources (meeting notes, meeting transcripts, Slack)

- **Status:** proposed (Wave 4). Evidence from official documentation and one live public
  fetch. Live API calls for Slack, Zoom, Microsoft Teams and Google Meet are still owed
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
- Drive API `files.export` of the v1.38 notes with an API key, and the notes' licence.
- The chosen meeting tool: one real transcript fetched end to end.
