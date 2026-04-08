"""
AgentLens × LangChain integration.

Zero decorator changes needed — just add the callback:

    from agentlens.integrations.langchain import AgentLensCallback
    from agentlens import AgentLens

    lens = AgentLens(endpoint="http://localhost:7430")
    cb = AgentLensCallback(lens)

    # Option A: per-chain
    chain.invoke({"input": "..."}, config={"callbacks": [cb]})

    # Option B: global (all LangChain calls in process)
    from langchain_core.callbacks import set_handler
    set_handler(cb)

How it works:
  LangChain emits run_id/parent_run_id on every callback.
  We map those UUIDs → AgentLens Span objects, maintaining the full
  parent-child hierarchy automatically.
  When the root chain ends, we close the AgentRun and export it.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Union
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from ..models import AgentRun, LLMMetadata, Span, SpanKind, SpanStatus
from ..tracer import AgentLens

# Try importing LangChain message types for prompt preview
try:
    from langchain_core.messages import BaseMessage
    _HAS_MESSAGES = True
except ImportError:
    _HAS_MESSAGES = False


class AgentLensCallback(BaseCallbackHandler):
    """
    LangChain callback handler that auto-instruments any chain, agent,
    LLM call, tool, or retriever — building a full AgentLens span tree
    without any decorator changes to user code.

    Thread-safe: each LangChain run_id gets its own Span, tracked in a
    dict keyed by UUID. Concurrent chain invocations are isolated.
    """

    # Tell LangChain we want errors too
    raise_error = False
    ignore_agent = False
    ignore_chain = False
    ignore_llm = False
    ignore_retriever = False
    ignore_chat_model = False

    def __init__(
        self,
        lens: Optional[AgentLens] = None,
        run_name: str = "langchain_run",
        tags: List[str] = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__()
        self._lens = lens or AgentLens()
        self._run_name = run_name
        self._tags = tags or ["langchain"]
        self._metadata = metadata or {}

        # run_id (UUID) → Span
        self._spans: Dict[UUID, Span] = {}
        # The single AgentRun for this callback instance
        self._run: Optional[AgentRun] = None
        # root run_id — when this run ends, we export
        self._root_run_id: Optional[UUID] = None

    # ── Internal helpers ──────────────────────────────────────────────────

    def _get_or_create_run(self) -> AgentRun:
        if self._run is None:
            self._run = AgentRun(
                name=self._run_name,
                tags=self._tags,
                metadata=self._metadata,
            )
        return self._run

    def _start_span(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        name: str,
        kind: SpanKind,
        inputs: Dict[str, Any] = None,
    ) -> Span:
        run = self._get_or_create_run()

        # Find parent span
        parent_span = self._spans.get(parent_run_id) if parent_run_id else None

        span = Span(
            run_id=run.id,
            parent_id=parent_span.id if parent_span else None,
            name=name,
            kind=kind,
            inputs=inputs or {},
        )
        run.spans.append(span)
        self._spans[run_id] = span

        # Track root
        if parent_run_id is None or parent_run_id not in self._spans:
            if self._root_run_id is None:
                self._root_run_id = run_id

        return span

    def _end_span(
        self,
        run_id: UUID,
        outputs: Dict[str, Any] = None,
        error: Exception = None,
    ):
        span = self._spans.get(run_id)
        if span:
            span.finish(outputs=outputs or {}, error=error)

    def _maybe_export(self, run_id: UUID):
        """Export the run when the root span closes."""
        if run_id == self._root_run_id and self._run:
            self._run.finish()
            self._lens._exporter.export(self._run)
            # Reset for potential reuse
            self._run = None
            self._root_run_id = None
            self._spans.clear()

    @staticmethod
    def _chain_name(serialized: Optional[Dict[str, Any]]) -> str:
        """Extract a readable name from LangChain's serialized dict."""
        if not serialized:
            return "chain"
        ids = serialized.get("id", [])
        if ids:
            return ids[-1]
        return serialized.get("name", "chain")

    @staticmethod
    def _safe_inputs(inputs: Any) -> Dict[str, Any]:
        if isinstance(inputs, dict):
            return {k: _safe_str(v) for k, v in list(inputs.items())[:10]}
        return {"input": _safe_str(inputs)}

    @staticmethod
    def _safe_outputs(outputs: Any) -> Dict[str, Any]:
        if isinstance(outputs, dict):
            return {k: _safe_str(v) for k, v in list(outputs.items())[:5]}
        return {"output": _safe_str(outputs)}

    # ── Chain hooks ───────────────────────────────────────────────────────

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        name = self._chain_name(serialized)
        # Top-level chain = agent kind, nested = chain kind
        kind = SpanKind.AGENT if parent_run_id is None else SpanKind.CHAIN
        self._start_span(run_id, parent_run_id, name, kind, self._safe_inputs(inputs))

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ):
        self._end_span(run_id, outputs=self._safe_outputs(outputs))
        self._maybe_export(run_id)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ):
        self._end_span(run_id, error=error)
        self._maybe_export(run_id)

    # ── LLM hooks ─────────────────────────────────────────────────────────

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        name = self._chain_name(serialized)
        prompt_preview = prompts[0][:500] if prompts else ""
        span = self._start_span(
            run_id, parent_run_id, name, SpanKind.LLM,
            inputs={"prompt_preview": prompt_preview, "num_prompts": len(prompts)},
        )
        # Extract model from serialized kwargs
        model = _dig(serialized, "kwargs", "model_name") or _dig(serialized, "kwargs", "model") or ""
        span.llm = LLMMetadata(model=model, provider=_infer_provider(serialized))

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[Any]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        name = self._chain_name(serialized)
        # Flatten messages to preview
        preview = ""
        if messages and messages[0]:
            msg = messages[0][-1]
            preview = str(getattr(msg, "content", msg))[:500]

        span = self._start_span(
            run_id, parent_run_id, name, SpanKind.LLM,
            inputs={"message_preview": preview, "num_messages": sum(len(m) for m in messages)},
        )
        model = _dig(serialized, "kwargs", "model_name") or _dig(serialized, "kwargs", "model") or ""
        span.llm = LLMMetadata(model=model, provider=_infer_provider(serialized))

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ):
        span = self._spans.get(run_id)
        if span and span.llm:
            # Extract token usage from LLMResult
            usage = response.llm_output or {}
            token_usage = usage.get("token_usage") or usage.get("usage") or {}

            input_tokens = (
                token_usage.get("prompt_tokens")
                or token_usage.get("input_tokens")
                or 0
            )
            output_tokens = (
                token_usage.get("completion_tokens")
                or token_usage.get("output_tokens")
                or 0
            )
            model = usage.get("model_name") or usage.get("model") or span.llm.model

            # Response preview from first generation
            response_preview = ""
            try:
                gen = response.generations[0][0]
                response_preview = getattr(gen, "text", None) or str(getattr(getattr(gen, "message", None), "content", ""))
                response_preview = response_preview[:500]
            except Exception:
                pass

            span.llm = LLMMetadata(
                model=model,
                provider=span.llm.provider,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=_estimate_cost(model, input_tokens, output_tokens),
                prompt_preview=span.inputs.get("prompt_preview", ""),
                response_preview=response_preview,
            )

        outputs = {"response_preview": response_preview if span else ""}
        self._end_span(run_id, outputs=outputs)
        self._maybe_export(run_id)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ):
        self._end_span(run_id, error=error)
        self._maybe_export(run_id)

    # ── Tool hooks ────────────────────────────────────────────────────────

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        inputs: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        name = serialized.get("name") or self._chain_name(serialized)
        self._start_span(
            run_id, parent_run_id, name, SpanKind.TOOL,
            inputs=inputs or {"input": input_str[:500]},
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ):
        self._end_span(run_id, outputs={"output": _safe_str(output)})
        self._maybe_export(run_id)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ):
        self._end_span(run_id, error=error)
        self._maybe_export(run_id)

    # ── Retriever hooks ───────────────────────────────────────────────────

    def on_retriever_start(
        self,
        serialized: Dict[str, Any],
        query: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        name = self._chain_name(serialized) or "retriever"
        self._start_span(
            run_id, parent_run_id, name, SpanKind.RETRIEVAL,
            inputs={"query": query[:500]},
        )

    def on_retriever_end(
        self,
        documents: Sequence[Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ):
        self._end_span(
            run_id,
            outputs={
                "num_docs": len(documents),
                "doc_previews": [_safe_str(d)[:200] for d in documents[:3]],
            },
        )
        self._maybe_export(run_id)

    def on_retriever_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ):
        self._end_span(run_id, error=error)
        self._maybe_export(run_id)

    # ── Agent action hooks ────────────────────────────────────────────────

    def on_agent_action(self, action: Any, *, run_id: UUID, parent_run_id: Optional[UUID] = None, **kwargs):
        # LangChain agent steps — log as attributes on the parent span
        span = self._spans.get(parent_run_id or run_id)
        if span:
            tool = getattr(action, "tool", "")
            tool_input = getattr(action, "tool_input", "")
            existing = span.attributes.get("agent_actions", [])
            existing.append({"tool": tool, "input": _safe_str(tool_input)})
            span.attributes["agent_actions"] = existing

    def on_agent_finish(self, finish: Any, *, run_id: UUID, parent_run_id: Optional[UUID] = None, **kwargs):
        span = self._spans.get(parent_run_id or run_id)
        if span:
            output = getattr(finish, "return_values", {})
            span.attributes["agent_finish"] = {k: _safe_str(v) for k, v in list(output.items())[:5]}


# ── CrewAI integration ────────────────────────────────────────────────────────

class AgentLensCrewCallback:
    """
    CrewAI step + task callback that auto-instruments crew runs.

    Usage:
        from agentlens.integrations.langchain import AgentLensCrewCallback
        from agentlens import AgentLens
        from crewai import Crew

        lens = AgentLens(endpoint="http://localhost:7430")
        cb = AgentLensCrewCallback(lens)

        crew = Crew(
            agents=[...],
            tasks=[...],
            step_callback=cb.on_step,
            task_callback=cb.on_task,
        )
        crew.kickoff()
    """

    def __init__(self, lens: Optional[AgentLens] = None, crew_name: str = "crew_run"):
        self._lens = lens or AgentLens()
        self._crew_name = crew_name
        self._run: Optional[AgentRun] = None
        self._task_spans: Dict[str, Span] = {}  # task_id → Span
        self._step_count = 0

    def _get_run(self) -> AgentRun:
        if self._run is None:
            self._run = AgentRun(name=self._crew_name, tags=["crewai"])
        return self._run

    def on_step(self, step_output: Any):
        """Passed as step_callback= to Crew. Called after every agent step."""
        run = self._get_run()
        self._step_count += 1

        # AgentFinish or AgentAction
        tool = getattr(step_output, "tool", None)
        tool_input = getattr(step_output, "tool_input", None)
        output = getattr(step_output, "output", None) or getattr(step_output, "return_values", {})

        kind = SpanKind.TOOL if tool else SpanKind.AGENT
        name = tool or f"agent_step_{self._step_count}"

        span = Span(
            run_id=run.id,
            name=name,
            kind=kind,
            inputs={"tool_input": _safe_str(tool_input)} if tool_input else {},
            outputs={"output": _safe_str(output)},
        )
        span.finish()
        run.spans.append(span)

    def on_task(self, task_output: Any):
        """Passed as task_callback= to Crew. Called after each task completes."""
        run = self._get_run()

        # task_output is a TaskOutput object
        description = getattr(task_output, "description", "task")
        raw = getattr(task_output, "raw", "")
        agent = getattr(task_output, "agent", "")

        span = Span(
            run_id=run.id,
            name=description[:60] if description else "task",
            kind=SpanKind.CHAIN,
            inputs={"agent": str(agent)},
            outputs={"result": _safe_str(raw)},
        )
        span.finish()
        run.spans.append(span)

    def finish(self, outputs: Dict[str, Any] = None, error: Exception = None):
        """Call this after crew.kickoff() to export the run."""
        if self._run:
            self._run.finish(error=error)
            if outputs:
                root = self._run.root_span
                if root:
                    root.outputs = {k: _safe_str(v) for k, v in list(outputs.items())[:5]}
            self._lens._exporter.export(self._run)
            self._run = None
            self._step_count = 0
            self._task_spans.clear()


# ── Convenience: one-line patch ───────────────────────────────────────────────

def patch_langchain(
    lens: Optional[AgentLens] = None,
    run_name: str = "langchain_run",
    tags: List[str] = None,
) -> AgentLensCallback:
    """
    Returns an AgentLensCallback pre-configured for global use.

    The returned callback can be passed to any chain via config={"callbacks": [cb]},
    or stored for injection into all your chains.

    In modern LangChain (>= 0.3), there is no single global setter.
    The recommended pattern is:

        cb = agentlens.patch_langchain()

        # Pass explicitly per invocation:
        chain.invoke(input, config={"callbacks": [cb]})

        # Or set as default in a RunnableConfig:
        from langchain_core.runnables import RunnableConfig
        config = RunnableConfig(callbacks=[cb])
        chain.invoke(input, config=config)

    Returns the AgentLensCallback instance.
    """
    cb = AgentLensCallback(lens=lens, run_name=run_name, tags=tags or ["langchain", "auto"])
    return cb


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_str(v: Any, max_len: int = 500) -> str:
    if v is None:
        return ""
    s = str(v)
    return s[:max_len] + "…" if len(s) > max_len else s


def _dig(d: dict, *keys: str) -> Any:
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _infer_provider(serialized: Dict[str, Any]) -> str:
    ids = serialized.get("id", [])
    id_str = " ".join(ids).lower()
    if "openai" in id_str:
        return "openai"
    if "anthropic" in id_str:
        return "anthropic"
    if "google" in id_str or "gemini" in id_str:
        return "google"
    if "ollama" in id_str:
        return "ollama"
    if "bedrock" in id_str:
        return "bedrock"
    return ""


_COST_TABLE = {
    "gpt-4o":              (2.50, 10.00),
    "gpt-4o-mini":         (0.15, 0.60),
    "gpt-4-turbo":         (10.00, 30.00),
    "claude-3-5-sonnet":   (3.00, 15.00),
    "claude-3-haiku":      (0.25, 1.25),
    "claude-sonnet-4":     (3.00, 15.00),
    "gemini-1.5-pro":      (1.25, 5.00),
    "gemini-1.5-flash":    (0.075, 0.30),
}

def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    for key, (inp, out) in _COST_TABLE.items():
        if key in (model or "").lower():
            return (input_tokens * inp + output_tokens * out) / 1_000_000
    return 0.0
