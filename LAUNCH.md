# AgentLens Launch Strategy

## HN Post (copy-paste ready)

**Title:**
AgentLens – open source observability for AI agents (DAG graph, run diffing, budget guards)

**Text:**
```
Hi HN,

I built AgentLens because I kept hitting the same wall: my agent failed in production
and I had no idea which step broke, why it branched the way it did, or what was
different from yesterday's run that worked.

Langfuse and Helicone are great for tracing individual LLM calls. But agents aren't a
single call — they're a graph of decisions: tools firing, sub-agents branching, retrieval
steps, retries. None of the existing tools give you that picture.

AgentLens does three things none of the existing tools do:

1. **Agent execution DAG** — your agent's full run as an interactive graph, color-coded
   by step type (agent/tool/LLM/retrieval) and status, with zoom/pan and click-to-inspect.

2. **Run diffing** — pick any two runs and see a side-by-side span comparison: which
   steps got slower, which status flipped, what steps only exist in one run.

3. **Budget guards** — set max token or cost limits per run; the SDK surfaces an
   `ok: false` signal you can check mid-execution to bail early.

The SDK is zero-dependency Python, works with any agent framework (LangChain, CrewAI,
custom), and auto-detects token usage from OpenAI and Anthropic responses.

Usage is three decorators:

    @lens.trace("my_agent", max_cost_usd=0.10)
    def my_agent(query):
        docs = retrieve(query)      # @lens.span auto-captures this
        return call_llm(docs)       # @lens.llm_call auto-extracts tokens

The server is FastAPI + Postgres + a React/D3 UI. One `docker compose up` to run
everything. Self-hostable, Apache 2.0.

GitHub: https://github.com/agentlens/agentlens
pip install agentlens

Would love feedback — especially from anyone who's built production agents and hit
the debugging wall I described.
```

---

## Launch checklist

### Pre-launch (do these before posting)

- [ ] Push to GitHub with clean history
- [ ] Add a real screenshot to docs/dag-screenshot.png (grab from running demo)
- [ ] `pip install agentlens` works on a fresh virtualenv
- [ ] `docker compose up` works end-to-end on a clean machine
- [ ] Add GitHub topics: `ai`, `agents`, `observability`, `llm`, `opentelemetry`, `python`, `typescript`, `self-hosted`
- [ ] Set up GitHub Discussions (for community questions)
- [ ] Write pinned issue: "Roadmap + feedback wanted"

### Launch day

- [ ] Post to HN (best time: 9–11am ET on Tuesday/Wednesday)
- [ ] Post to r/LocalLLaMA (strong self-hosted audience)
- [ ] Post to r/MachineLearning 
- [ ] Post to r/LangChain
- [ ] Cross-post to Twitter/X with a short demo GIF (record DAG + diff in action)
- [ ] Post to LangChain Discord #show-and-tell
- [ ] Post to Hugging Face Discord
- [ ] DM 5–10 people building agents you know personally

### Post-launch (week 1)

- [ ] Reply to every HN comment within 2 hours
- [ ] File GitHub issues for every piece of feedback that's a valid feature request
- [ ] Write a short blog post: "How we built the DAG layout engine without d3.tree()"
  (technical depth drives developer respect)
- [ ] Reach out to LangChain / CrewAI teams about native integration

---

## Monetization path (when ready)

**Open source core stays free forever.**

Cloud hosted tier at $9/month:
- Persistent storage (core gives you 7-day retention)
- Team sharing — share run links with teammates
- Slack / email alerts on budget exceeded or error spike
- Priority support

This is the exact model Langfuse used. They raised $4M after ~6 months of traction.

The pricing is deliberately low — $9 is "I'll expense this without thinking" territory
for any dev at a company. Volume matters more than margin at this stage.

---

## Comparable project trajectories

| Project | Category | Stars at 6mo | Raised |
|---|---|---|---|
| Langfuse | LLM observability | ~8k | $4M |
| Helicone | LLM observability | ~3k | $2.6M |
| Dify | LLM app builder | ~25k | $18M |
| Phoenix/Arize | LLM eval+tracing | ~4k | Existing co |

AgentLens is differentiated from all of these by the agent-specific DAG and diff views.
The market is clearly there (Langfuse's growth proved it). The timing is right — agent
usage exploded in 2025–2026 but observability tooling hasn't caught up.
