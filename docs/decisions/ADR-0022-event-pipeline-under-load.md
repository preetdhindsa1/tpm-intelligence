# ADR-0022: The event pipeline under real load (P3-M5)

- **Status:** accepted (owner approved the fixes, 2026-11-24)
- **Date:** 2026-11-24

## Context

P3-M5 measures how long a GitHub event takes to reach an open dashboard page (target:
p95 under 30 s, CLAUDE.md section 9). The first measurements on 2026-11-24 found that
typical events took 2-10 s, but some took 60 s to 14 minutes. Each slow case had a
different cause in how events move from Pub/Sub through the API's in-process worker
(ADR-0017) to the live page. None showed up in tests; all needed the real cloud,
real traffic, and the per-event measurement.

| What we saw | Cause |
|---|---|
| 79 s after a deploy | The old API revision stayed alive while live pages were open (5-10 min) and kept pulling. It pulled an event, shut down without acknowledging it, and Pub/Sub redelivered it after the 60 s ack deadline |
| 60-90 s at low traffic, idle worker | The worker pulled with a 2 s client timeout. Pub/Sub leased messages to requests the client had already abandoned; they stayed hidden until the 60 s ack deadline |
| Up to 14 min (5,000-message backlog) | Adding Kafka to the 5-minute poll plus the hourly Jira sync. The worker stored one event per transaction and acknowledged one message per call (about 500 events a minute) |
| 11 min with no push at all | A live stream compared the data version before and after its own refresh; when another page had refreshed first, it saw no change and stayed silent |
| ~355 s, but only 2-6 s after receipt | A measurement error: the push was timed by its batch's first event, which can be an issue's older history |

## Decision

1. **Clean hand-off between revisions.** Stopping hands back unprocessed messages at once
   (nack); the API stops its worker on shutdown; live streams end after 2 minutes, so an
   old revision is gone about 1.5 minutes after a deploy (measured: 1 min 36 s).
2. **Pull with at least a 20 s timeout** (`PubSubTransport.min_pull_timeout_s`). A pull
   still returns as soon as messages exist, so this adds no latency.
3. **Store and acknowledge a pulled batch at once** (up to 100 messages: one
   `INSERT ... ON CONFLICT DO NOTHING RETURNING event_id`, one ack call). Any batch failure
   falls back to one message at a time, which keeps retries and dead-lettering unchanged.
   New events are announced inside their own consumer span, so a trace still runs from
   the collector to the page. Local benchmark: 793 -> 4,147 events/s.
4. **Each live stream remembers the version it last sent** and pushes whenever the data is
   newer, whoever refreshed it.
5. **Measure every webhook event** (`observability.latency.per_event_latency`): each one is
   timed to the first push after it was stored, not one event per push.
6. **Backlog alert at 3 minutes held for 2** (was 10 for 5, which fired 18 minutes after a
   real backlog began).

## Alternatives considered

- **StreamingPull instead of synchronous pull.** Google's recommended low-latency client.
  It would replace the transport's pull model (and the Redis/in-memory symmetry). Kept as
  the next step if the 20 s pull is not enough.
- **A separate queue for webhook events** so they never wait behind polled ones. More
  infrastructure; batching removed the backlog instead.
- **Stop the poller republishing facts it has already seen.** It republishes every event of
  any PR that changed (Kafka: about 400-2,000 per run, mostly duplicates). Worth doing
  later; storing in batches makes the duplicates cheap enough for now.
- **Keep one event per transaction and add worker instances.** ADR-0017 runs exactly one
  in-process worker; more instances would also mean more API instances.

## Trade-offs and limits

- A shutdown that happens mid-pull can still leave a just-leased batch to the ack
  deadline; the 2-minute stream cap keeps that window short and rare.
- The 20 s pull means a stopping worker can take up to 20 s to exit its current pull.
- Batches commit as one transaction: one bad event fails the batch and falls back to one at
  a time for that pull.
- The measurements are one owner's activity on one repository: a small sample, labelled
  as such.

No AI is involved in any of this: it is queueing and storage.
