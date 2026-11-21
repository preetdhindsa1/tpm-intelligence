# ADR-0001: Event queue — Pub/Sub in the cloud, Redis Streams locally, one interface

- **Status:** accepted
- **Date:** 2026-11-21

## Context

Collectors (GitHub poller now; webhooks and Jira later) emit normalized events. Downstream
stages (linker, engine, forecast) consume them. Requirements from CLAUDE.md:

- Event-driven on Google Cloud (§3), with trace context carried in message attributes so
  one trace spans collector → worker → API (§9).
- Local development via `docker compose up`, with no cloud account needed.
- An alert on queue backlog growth (§9).
- Collectors re-poll the same facts, so delivery will contain duplicates.

## Decision

1. A byte-level `Transport` protocol (`publish`, `pull`, `ack`, `nack`, `dead_letter`) in
   `pipeline/queue.py`, with two implementations:
   - `PubSubTransport` (cloud): Google Cloud Pub/Sub with synchronous pull.
   - `RedisStreamsTransport` (local): Redis Streams with consumer groups.
   `QUEUE_BACKEND=redis|pubsub` selects one (`pipeline/factory.py`).
2. Typed `EventPublisher` / `EventConsumer` sit on top. They own serialization, OTel
   PRODUCER/CONSUMER spans (messaging semantic conventions), W3C `traceparent` injection
   and extraction via message attributes, metrics, and retry/dead-letter policy. Backend
   code never sees tracing or event types.
3. **At-least-once delivery** everywhere. `event_id` is a deterministic UUIDv5 of the
   source fact, so handlers de-duplicate on it (enforced in Postgres in M2/M7).
4. Failed handling → `nack` → redelivery. After `max_delivery_attempts` (default 5) the
   message goes to `<topic>-dead-letter` (Pub/Sub) or `tpm:stream:<topic>:dead-letter` (Redis).

Redis Streams mapping: topic → stream; subscription → consumer group created at ID `0`
(a worker that starts late still sees earlier events); redelivery via `XAUTOCLAIM` after a
visibility timeout; Redis's delivery counter gives `delivery_attempt`; nack = `XCLAIM IDLE
<visibility> JUSTID` so the message can be reclaimed immediately.

## Alternatives considered

- **Pub/Sub emulator locally.** Same API as the cloud, but it is a ~1 GB image with no
  persistence and no dead-letter support. Redis is already in the stack for caching and SSE.
  The emulator is still used in an optional integration test (`PUBSUB_EMULATOR_HOST`) to
  prove the Pub/Sub adapter against the real client library.
- **Redis Pub/Sub (not Streams).** Fire-and-forget: no acks, no redelivery, no backlog
  metric. Rejected.
- **Kafka / Redpanda.** Strong, but a second heavy system to run, and no managed GCP
  equivalent that matches Cloud Run's scale-to-zero cost profile.
- **Cloud Tasks / Eventarc.** Push-based HTTP delivery couples queue semantics to the API
  service. Pub/Sub push may be revisited for the worker on Cloud Run (see trade-offs).
- **Celery / RQ.** Task queues, not event logs; they would hide trace propagation and
  fan-out to several subscriptions.

## Trade-offs and consequences

- Two backends must keep the same behaviour. Mitigation: one contract test suite runs
  against fakeredis (unit), real Redis and the Pub/Sub emulator (`make test-integration`).
- Ordering is not guaranteed (Pub/Sub without ordering keys; Redis reclaim reorders).
  Consumers must rely on `occurred_at`, not arrival order. This matters for the
  #6395 history: removal at 12:05:57Z and re-add at 2026-11-21 00:33:55Z must be ordered
  by timestamp, not by delivery.
- The Redis stream is capped (`MAXLEN ~ 500k`). If a consumer falls that far behind, the
  oldest unread events are dropped. That is acceptable because Postgres is the source of
  truth and pollers can re-sync; the backlog alert should fire long before.
- Synchronous pull suits a long-running worker. On Cloud Run that needs min-instances ≥ 1
  or a Cloud Run job. Switching to Pub/Sub push would mean a small HTTP adapter around the
  same `EventConsumer._process` logic. Decide in M9.

## AI vs rules

No AI involved.
