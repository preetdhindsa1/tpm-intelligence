# Langfuse (self-hosted, local)

LLM traces for the agents (ADR-0009). Separate Compose project so the main stack stays light.

```bash
make langfuse-up     # http://localhost:3001  (login: LANGFUSE_INIT_USER_EMAIL / _PASSWORD from .env)
make langfuse-down
```

The app sends only AI spans (`ai.*` and the Anthropic SDK's GenAI spans) to Langfuse over
OTLP, using `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`
(`observability/langfuse_export.py`). Jaeger still receives every span.

`docker-compose.yml` is Langfuse's file, vendored unchanged at v4.83.0. To upgrade, replace it
with the file from a newer release tag and keep `compose.override.yml`. The upstream
`# CHANGEME` passwords stay at their defaults: no Langfuse port except the UI on 127.0.0.1
is published, and it holds only public-data traces. Change them before any shared use.
