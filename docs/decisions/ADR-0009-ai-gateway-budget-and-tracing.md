# ADR-0009: AI gateway, daily budget, caching and LLM tracing

- **Status:** accepted
- **Date:** 2026-11-22

## Context

Phase 2 agents call Claude. CLAUDE.md §8 sets the rules:

- Agents receive only engine facts and return structured claims.
- Model names come from config: a cheaper model for simple tasks, a stronger one for
  summaries.
- Results are cached by a hash of the input facts.
- AI runs only when facts change meaningfully.
- A daily budget applies: slow down at 80%, pause non-essential AI at 100%.

§9 adds an alert at 80% spend, and observability from day one. The owner set the cap to
**$2/day** and chose **self-hosted Langfuse**.

## Decision

1. **One gateway** (`agents/gateway.py`) is the only path to Claude. Each call goes
   fingerprint → cache → budget → Claude → cost → cache write, and every attempt is
   written to `ai_usage`. That includes cache hits, budget denials, refusals, truncations
   and errors.
2. **Structured output.**
   - Calls use `client.beta.messages.parse(output_format=<Pydantic model>)` with the
     Anthropic SDK (2.x).
   - Agents return `ClaimsOut`, which converts to `verify.Claim` for the fact checker
     (ADR-0008). Fact-check counts are stored next to the cached result.
   - A refusal or a truncated output is never cached or shown.
3. **Models from config** (`AI_MODEL_SIMPLE=claude-haiku-5-5`,
   `AI_MODEL_SUMMARY=claude-opus-5-5`). A task names a *role*, never a model.
   - Effort and `max_tokens` are set per task.
   - Calls on the summary model opt into server-side refusal fallbacks
     (`fallbacks: "default"`). Haiku has none.
4. **Budget** (`agents/budget.py`, pure).
   - Spend is summed from `ai_usage` for the UTC day.
   - Each check adds the call's **worst-case** cost (prompt size plus the full
     `max_tokens`), so one call can't jump far past the cap.
   - From 80%, non-essential calls are spaced 60 s apart. At 100% they pause.
   - Essential calls (ones a TPM asked for) may exceed the cap only by
     `AI_ESSENTIAL_OVERAGE`. The default is 0, so **$2 is a hard cap**.
   - A refusal fallback bills each model separately, read from `usage.iterations`.
   - Unknown models are charged at the most expensive known rate.
5. **Cache key** (`agents/fingerprint.py`): SHA-256 of task + prompt-text SHA + model +
   canonical input facts. Editing a prompt file changes the key.
6. **Re-run threshold** (`agents/rerun.py`, pure). Re-run only when odds move by
   `AI_ODDS_CHANGE_POINTS` (10) or any non-odds fact changes. Range and base-rate jitter
   are ignored.
7. **Prompts** are versioned files, `agents/prompts/<name>.v<N>.md`, loaded by name and
   version.
8. **Tracing.**
   - The gateway opens an `ai.<task>` span with task, prompt version, model, budget
     state, outcome and cost. The Anthropic SDK adds GenAI child spans, with prompt and
     response content when `AI_TRACE_CONTENT=true`; the data is public.
   - Jaeger / Cloud Trace get every span. **Langfuse gets only AI spans**, through a
     filtering span processor that sends OTLP to `/api/public/otel`
     (`observability/langfuse_export.py`), so one instrumentation path serves both.
   - Metrics: `ai.calls`, `ai.cost`, `ai.tokens` and `ai.budget.used_fraction`. The
     80% alert is in `infra/monitoring.tf`.
9. **Langfuse runs self-hosted** as a separate Compose project (`make langfuse-up`,
   http://localhost:3001):
   - Upstream v4.83.0 compose file, vendored unchanged, plus a local override that
     publishes only the UI on 127.0.0.1 and turns off Langfuse's own telemetry.
   - The project and keys are created at startup from `.env`.

## Alternatives considered

- **Langfuse Python SDK decorators.** That would be a second instrumentation path next to
  OpenTelemetry. Langfuse v4 ingests OTLP natively, so the SDK isn't needed.
- **Langfuse spans through the shared OTel Collector.** The collector can't drop
  Langfuse's export cleanly when Langfuse isn't running, and it would forward every
  span. App-side filtering is explicit and testable.
- **Langfuse Cloud.** Less to run, but the owner chose self-hosting. Traces contain only
  public data either way.
- **Budget from the Anthropic Usage API.** It is authoritative but delayed and needs an
  admin key. The local ledger is immediate and errs high, because it charges worst-case
  estimates before the call and real usage after it.
- **LangGraph in M2.** It isn't needed until M3 has multi-step agents. The gateway is
  what every graph node will call.

## Trade-offs and consequences

- **Prices are a checked-in table** (as of 2026-11-03). If Anthropic changes prices, the
  table must be updated. Unknown models fail safe, at the highest rate.
- **The ledger never sees spend outside the platform.** The Console's own spend limit is
  the backstop.
- **Self-hosted Langfuse adds six containers** (web, worker, Postgres, ClickHouse, Redis,
  MinIO). They run only when asked (`make langfuse-up`). In the cloud, Langfuse is out of
  scope for Phase 2. The cloud key secret and the budget alert are in Terraform.
- **Langfuse v4 no longer offers its old trace-read API.** Checks use
  `/api/public/v2/observations`.

## AI vs rules

AI produces only `ClaimsOut`, which the fact checker verifies. Everything that decides
whether, when and how much AI runs is deterministic code: budget, cache, re-run
thresholds and cost.
