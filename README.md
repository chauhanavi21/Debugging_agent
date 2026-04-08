# 🔭 AgentLens

**Open source observability runtime for AI agents.**

Langfuse traces LLM calls. AgentLens traces *agents* — every step, every tool, every branch, in a visual DAG you can actually debug.

![AgentLens DAG screenshot](docs/dag-screenshot.png)

---

## The problem

Your agent failed in production. You have no idea which step broke, why it branched the way it did, or how this run differed from yesterday's successful one.

LLM call tracers (Langfuse, Helicone) give you individual prompt/response pairs. But agents aren't a single LLM call — they're a *graph* of decisions: tools firing, sub-agents spawning, retrieval steps, retries. None of the existing tools give you that full picture.

AgentLens does.

---

## Features

| | AgentLens | Langfuse | Helicone |
|---|---|---|---|
| LLM call tracing | ✅ | ✅ | ✅ |
| **Agent execution graph (DAG)** | ✅ | ❌ | ❌ |
| **Step-by-step replay** | ✅ | ❌ | ❌ |
| **Run diffing** | ✅ | ❌ | ❌ |
| **Budget guards** | ✅ | ❌ | ❌ |
| Self-hostable | ✅ | ✅ | ❌ |
| Zero required deps (SDK) | ✅ | ❌ | ❌ |
| Framework agnostic | ✅ | ✅ | ✅ |

---

## Quickstart

### 1. Instrument your agent

```bash
pip install agentlens
```

```python
from agentlens import AgentLens, SpanKind

lens = AgentLens(endpoint="http://localhost:7430")

@lens.trace("research_agent", max_cost_usd=0.10)
def research_agent(query: str) -> str:
    docs = retrieve_docs(query)
    answer = call_llm(docs, query)
    return format_answer(answer)

@lens.span("retrieve_docs", kind=SpanKind.RETRIEVAL)
def retrieve_docs(query: str) -> list:
    ...

@lens.tool("format_answer")
def format_answer(answer: str) -> str:
    ...
```

Every decorated function becomes a node in the DAG. Nesting is captured automatically.

### 2. Run the server (Docker)

```bash
git clone https://github.com/agentlens/agentlens
cd agentlens
docker compose up
```

That's it. Open `http://localhost:5173`.

### 3. What you'll see

- **Sidebar** — every agent run, filterable by status/name/tag, live-polling
- **DAG view** — your agent's execution tree, color-coded by span kind and status
- **Span detail** — click any node: inputs, outputs, LLM prompt/response, token counts, cost, error stack
- **Run diff** — pick two runs, see exactly which steps got slower, which status flipped, what changed

---

## SDK reference

### Zero-config global decorators

```python
from agentlens import trace, tool

@trace("my_agent")          # creates an AgentRun
def my_agent(query): ...

@tool("web_search")         # creates a child Span
def web_search(query): ...
```

### Full client with options

```python
from agentlens import AgentLens, SpanKind
from agentlens.exporters import FileExporter

lens = AgentLens(
    endpoint="http://localhost:7430",   # send to server
    api_key="your-key",                 # optional auth
    # exporter=FileExporter("runs.jsonl")  # or write to file
)

@lens.trace(
    "my_agent",
    tags=["prod", "rag"],
    max_total_tokens=5000,    # pause if exceeded
    max_cost_usd=0.05,        # pause if exceeded
)
def my_agent(query): ...

@lens.span("retrieve", kind=SpanKind.RETRIEVAL)
def retrieve(query): ...

@lens.llm_call("chat", model="gpt-4o")
def chat(prompt): ...         # auto-extracts token usage from OpenAI/Anthropic responses
```

### Async support

Works identically — just `async def` your functions.

```python
@lens.trace("async_agent")
async def async_agent(query: str):
    results = await search(query)
    return await summarize(results)
```

### Budget guards

```python
@lens.trace("expensive_agent", max_total_tokens=10_000, max_cost_usd=0.25)
def expensive_agent(query):
    for i in range(20):
        budget = lens.check_budget()
        if not budget["ok"]:
            return f"Stopped at step {i} — budget exceeded"
        result = call_llm(query)
    return result
```

### Manual run/span control

```python
run = lens.start_run("my_agent", tags=["prod"])
span = lens.start_span("retrieve", kind=SpanKind.RETRIEVAL)
try:
    docs = retrieve(query)
    lens.finish_span(span, outputs={"docs": docs})
except Exception as e:
    lens.finish_span(span, error=e)
    raise
finally:
    lens.finish_run(run)
```

### Exporters

```python
from agentlens.exporters import ConsoleExporter, FileExporter, HttpExporter

# Print summary to stdout (default when no endpoint set)
lens = AgentLens(exporter=ConsoleExporter())

# Write JSONL for offline replay or CI pipelines
lens = AgentLens(exporter=FileExporter("runs.jsonl"))

# Ship to server (background thread, non-blocking)
lens = AgentLens(endpoint="http://your-server:7430")
```

---

## Server API

All endpoints return JSON.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/ingest/run` | Receive a completed run from the SDK |
| `GET` | `/api/runs` | List runs with filters + pagination |
| `GET` | `/api/runs/{id}` | Full run detail with span tree |
| `POST` | `/api/runs/diff` | Compare two runs |
| `GET` | `/api/analytics/stats` | Dashboard summary |
| `GET` | `/api/analytics/slow-spans` | Slowest spans by avg duration |
| `GET` | `/api/analytics/model-usage` | Token + cost per LLM model |

### List runs with filters

```bash
GET /api/runs?status=error&name=research&tag=prod&limit=20
```

### Diff two runs

```bash
POST /api/runs/diff
{"run_id_a": "abc-123", "run_id_b": "def-456"}
```

Returns per-span comparison: duration delta, status changes, spans only in one run.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Your Agent Code                       │
│  @lens.trace  @lens.span  @lens.tool  @lens.llm_call    │
└─────────────────┬───────────────────────────────────────┘
                  │  AgentRun JSON (background thread)
                  ▼
┌─────────────────────────────────────────────────────────┐
│              AgentLens Server (FastAPI)                  │
│  POST /api/ingest/run                                    │
│  GET  /api/runs  GET /api/runs/:id  POST /api/runs/diff  │
└─────────────────┬───────────────────────────────────────┘
                  │
        ┌─────────┴──────────┐
        │    PostgreSQL       │
        │  runs + spans       │
        │  JSONB + GIN index  │
        └─────────┬──────────┘
                  │
┌─────────────────┴───────────────────────────────────────┐
│                 AgentLens UI (React + D3)                │
│  DAG graph · span drawer · run diff · live polling       │
└─────────────────────────────────────────────────────────┘
```

---

## Self-hosting

### Docker Compose (recommended)

```bash
docker compose up          # postgres + server + ui
# Server: http://localhost:7430
# UI:     http://localhost:5173
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://agentlens:agentlens@postgres:5432/agentlens` | Postgres connection |
| `AGENTLENS_API_KEY` | `""` (no auth) | Require this key on all ingest requests |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
| `VITE_API_URL` | `""` (demo mode) | UI → server URL |

### Production checklist

- [ ] Set `AGENTLENS_API_KEY` to a strong random string
- [ ] Use a managed Postgres (RDS, Supabase, Neon)
- [ ] Put the server behind nginx/Caddy with TLS
- [ ] Set `CORS_ORIGINS` to your UI domain only
- [ ] Mount a persistent volume for Postgres data

---

## Roadmap

- [ ] **Webhook alerts** — Slack/email when a run exceeds budget or errors
- [ ] **Eval integration** — attach Ragas/custom eval scores to runs
- [ ] **Timeline view** — Gantt-style waterfall alongside the DAG
- [ ] **LangGraph / CrewAI / AutoGPT native integrations**
- [ ] **Cloud hosted** — managed AgentLens with team sharing ($9/mo)
- [ ] **TypeScript SDK** — for LangChain.js and other JS agent frameworks
- [ ] **OTEL bridge** — export spans as OpenTelemetry traces

---

## Contributing

```bash
git clone https://github.com/agentlens/agentlens
cd agentlens

# SDK dev
cd sdk && pip install -e ".[dev]" && python test_sdk.py

# Server dev (needs postgres)
cd server && pip install -e . && uvicorn agentlens_server.main:app --reload --port 7430

# UI dev
cd ui && npm install && npm run dev
```

PRs welcome. Check `CONTRIBUTING.md` for the full guide.

---

## License

Apache 2.0 — free to use, modify, and self-host. Commercial use permitted.

---

<div align="center">
  Built with frustration after the 40th time asking "why did my agent fail?" ·
  <a href="https://github.com/agentlens/agentlens/issues">Issues</a> ·
  <a href="https://github.com/agentlens/agentlens/discussions">Discussions</a>
</div>
