"""
AgentLens Tracer — the main user-facing API.

Usage:
    lens = AgentLens(endpoint="http://localhost:7430")

    @lens.trace("my_agent", kind=SpanKind.AGENT)
    def my_agent(query: str):
        result = call_llm(query)
        return result

    @lens.tool("web_search")
    def web_search(query: str):
        ...

Or as a global singleton:
    from agentlens import trace, tool

    @trace("my_agent")
    def my_agent(...): ...
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import os
import time
from typing import Any, Callable, Optional, TypeVar, overload

from .context import get_current_run, get_current_span, set_current_run, set_current_span
from .exporters import BaseExporter, ConsoleExporter, HttpExporter
from .models import AgentRun, LLMMetadata, Span, SpanKind, SpanStatus

logger = logging.getLogger("agentlens")

F = TypeVar("F", bound=Callable)


class AgentLens:
    """
    The main AgentLens client.
    One instance per process is typical; configure once, use everywhere.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: str = "",
        exporter: Optional[BaseExporter] = None,
        enabled: bool = True,
    ):
        self.enabled = enabled

        if exporter:
            self._exporter = exporter
        elif endpoint or os.getenv("AGENTLENS_ENDPOINT"):
            url = endpoint or os.getenv("AGENTLENS_ENDPOINT", "http://localhost:7430")
            key = api_key or os.getenv("AGENTLENS_API_KEY", "")
            self._exporter = HttpExporter(endpoint=url, api_key=key)
        else:
            self._exporter = ConsoleExporter()

    # ------------------------------------------------------------------
    # Low-level: manual run / span management
    # ------------------------------------------------------------------

    def start_run(
        self,
        name: str,
        tags: list[str] = None,
        metadata: dict = None,
        max_total_tokens: int = None,
        max_cost_usd: float = None,
    ) -> AgentRun:
        run = AgentRun(
            name=name,
            tags=tags or [],
            metadata=metadata or {},
            max_total_tokens=max_total_tokens,
            max_cost_usd=max_cost_usd,
        )
        set_current_run(run)
        return run

    def finish_run(self, run: AgentRun, error: Exception = None):
        run.finish(error=error)
        if self.enabled:
            self._exporter.export(run)
        set_current_run(None)
        set_current_span(None)

    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.CUSTOM,
        inputs: dict = None,
        attributes: dict = None,
    ) -> Span:
        run = get_current_run()
        parent = get_current_span()

        span = Span(
            run_id=run.id if run else "",
            parent_id=parent.id if parent else None,
            name=name,
            kind=kind,
            inputs=inputs or {},
            attributes=attributes or {},
        )

        if run:
            run.spans.append(span)

        set_current_span(span)
        return span

    def finish_span(self, span: Span, outputs: dict = None, error: Exception = None):
        span.finish(outputs=outputs, error=error)
        # Restore parent span to context
        run = get_current_run()
        if run:
            parent_id = span.parent_id
            parent = next((s for s in run.spans if s.id == parent_id), None)
            set_current_span(parent)

    # ------------------------------------------------------------------
    # Budget guard — call inside a traced function to check limits
    # ------------------------------------------------------------------

    def check_budget(self, run: AgentRun = None) -> dict:
        run = run or get_current_run()
        if run is None:
            return {"ok": True}
        d = run.to_dict()["budget"]
        exceeded = d["tokens_exceeded"] or d["cost_exceeded"]
        return {"ok": not exceeded, **d}

    # ------------------------------------------------------------------
    # Decorators
    # ------------------------------------------------------------------

    def trace(
        self,
        name: str = None,
        *,
        kind: SpanKind = SpanKind.AGENT,
        tags: list[str] = None,
        metadata: dict = None,
        max_total_tokens: int = None,
        max_cost_usd: float = None,
        capture_inputs: bool = True,
        capture_outputs: bool = True,
    ):
        """
        Decorator that creates a new AgentRun for the decorated function.
        Use this on your top-level agent entry point.

        @lens.trace("my_agent", max_cost_usd=0.10)
        def my_agent(query: str): ...
        """
        def decorator(fn: F) -> F:
            span_name = name or fn.__name__

            if asyncio.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def async_wrapper(*args, **kwargs):
                    if not self.enabled:
                        return await fn(*args, **kwargs)

                    run = self.start_run(
                        span_name,
                        tags=tags,
                        metadata=metadata,
                        max_total_tokens=max_total_tokens,
                        max_cost_usd=max_cost_usd,
                    )
                    span = self.start_span(span_name, kind=kind, inputs=_capture_args(fn, args, kwargs) if capture_inputs else {})
                    try:
                        result = await fn(*args, **kwargs)
                        self.finish_span(span, outputs={"result": _safe_repr(result)} if capture_outputs else {})
                        self.finish_run(run)
                        return result
                    except Exception as e:
                        self.finish_span(span, error=e)
                        self.finish_run(run, error=e)
                        raise
                return async_wrapper  # type: ignore
            else:
                @functools.wraps(fn)
                def sync_wrapper(*args, **kwargs):
                    if not self.enabled:
                        return fn(*args, **kwargs)

                    run = self.start_run(
                        span_name,
                        tags=tags,
                        metadata=metadata,
                        max_total_tokens=max_total_tokens,
                        max_cost_usd=max_cost_usd,
                    )
                    span = self.start_span(span_name, kind=kind, inputs=_capture_args(fn, args, kwargs) if capture_inputs else {})
                    try:
                        result = fn(*args, **kwargs)
                        self.finish_span(span, outputs={"result": _safe_repr(result)} if capture_outputs else {})
                        self.finish_run(run)
                        return result
                    except Exception as e:
                        self.finish_span(span, error=e)
                        self.finish_run(run, error=e)
                        raise
                return sync_wrapper  # type: ignore

        return decorator

    def span(
        self,
        name: str = None,
        *,
        kind: SpanKind = SpanKind.CHAIN,
        capture_inputs: bool = True,
        capture_outputs: bool = True,
    ):
        """
        Decorator for sub-steps within an agent run.
        Must be called inside a function already decorated with @lens.trace.

        @lens.span("retrieve_docs", kind=SpanKind.RETRIEVAL)
        def retrieve_docs(query: str): ...
        """
        def decorator(fn: F) -> F:
            span_name = name or fn.__name__

            if asyncio.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def async_wrapper(*args, **kwargs):
                    if not self.enabled:
                        return await fn(*args, **kwargs)
                    s = self.start_span(span_name, kind=kind, inputs=_capture_args(fn, args, kwargs) if capture_inputs else {})
                    try:
                        result = await fn(*args, **kwargs)
                        self.finish_span(s, outputs={"result": _safe_repr(result)} if capture_outputs else {})
                        return result
                    except Exception as e:
                        self.finish_span(s, error=e)
                        raise
                return async_wrapper  # type: ignore
            else:
                @functools.wraps(fn)
                def sync_wrapper(*args, **kwargs):
                    if not self.enabled:
                        return fn(*args, **kwargs)
                    s = self.start_span(span_name, kind=kind, inputs=_capture_args(fn, args, kwargs) if capture_inputs else {})
                    try:
                        result = fn(*args, **kwargs)
                        self.finish_span(s, outputs={"result": _safe_repr(result)} if capture_outputs else {})
                        return result
                    except Exception as e:
                        self.finish_span(s, error=e)
                        raise
                return sync_wrapper  # type: ignore

        return decorator

    def tool(self, name: str = None, **kwargs):
        """Shorthand for @lens.span(..., kind=SpanKind.TOOL)"""
        return self.span(name, kind=SpanKind.TOOL, **kwargs)

    def llm_call(
        self,
        name: str = None,
        *,
        model: str = "",
        provider: str = "",
        extract_usage: Callable = None,
    ):
        """
        Decorator for raw LLM calls. Captures token usage automatically.

        extract_usage: optional fn(result) -> LLMMetadata
        If not provided, AgentLens tries common response shapes (OpenAI, Anthropic).

        @lens.llm_call("chat_completion", model="gpt-4o")
        def call_openai(prompt: str): ...
        """
        def decorator(fn: F) -> F:
            span_name = name or fn.__name__

            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                if not self.enabled:
                    return fn(*args, **kwargs)
                s = self.start_span(span_name, kind=SpanKind.LLM)
                s.llm = LLMMetadata(model=model, provider=provider)
                try:
                    result = fn(*args, **kwargs)
                    # Try to extract usage
                    usage = None
                    if extract_usage:
                        usage = extract_usage(result)
                    else:
                        usage = _auto_extract_usage(result, model, provider)
                    if usage:
                        s.llm = usage
                    self.finish_span(s)
                    return result
                except Exception as e:
                    self.finish_span(s, error=e)
                    raise
            return wrapper  # type: ignore

        return decorator


# ------------------------------------------------------------------
# Global singleton — zero-config usage
# ------------------------------------------------------------------

_global_lens = AgentLens()


def trace(name: str = None, **kwargs):
    """Global @trace decorator. Uses console exporter by default."""
    return _global_lens.trace(name, **kwargs)


def tool(name: str = None, **kwargs):
    """Global @tool decorator."""
    return _global_lens.tool(name, **kwargs)


def configure(
    endpoint: str = None,
    api_key: str = "",
    exporter: BaseExporter = None,
    enabled: bool = True,
):
    """
    Configure the global AgentLens singleton.
    Call once at app startup before any decorators fire.
    """
    global _global_lens
    _global_lens = AgentLens(
        endpoint=endpoint,
        api_key=api_key,
        exporter=exporter,
        enabled=enabled,
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _capture_args(fn: Callable, args: tuple, kwargs: dict) -> dict:
    """Bind positional args to param names and merge with kwargs."""
    try:
        sig = inspect.signature(fn)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        return {k: _safe_repr(v) for k, v in bound.arguments.items()}
    except Exception:
        return {}


def _safe_repr(value: Any, max_len: int = 500) -> Any:
    """Convert a value to something JSON-serializable, truncated."""
    if isinstance(value, (str, int, float, bool, type(None))):
        if isinstance(value, str) and len(value) > max_len:
            return value[:max_len] + "…"
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_repr(v) for v in value[:20]]
    if isinstance(value, dict):
        return {k: _safe_repr(v) for k, v in list(value.items())[:20]}
    return repr(value)[:max_len]


def _auto_extract_usage(result: Any, model: str, provider: str) -> Optional[LLMMetadata]:
    """
    Try to extract token usage from common LLM response shapes.
    Supports: OpenAI ChatCompletion, Anthropic Message.
    """
    try:
        # OpenAI: result.usage.prompt_tokens / completion_tokens
        if hasattr(result, "usage") and hasattr(result.usage, "prompt_tokens"):
            u = result.usage
            input_t = getattr(u, "prompt_tokens", 0)
            output_t = getattr(u, "completion_tokens", 0)
            mdl = getattr(result, "model", model)
            response_text = ""
            try:
                response_text = result.choices[0].message.content or ""
            except Exception:
                pass
            return LLMMetadata(
                model=mdl,
                provider=provider or "openai",
                input_tokens=input_t,
                output_tokens=output_t,
                cost_usd=_estimate_cost(mdl, input_t, output_t),
                response_preview=response_text[:500],
            )

        # Anthropic: result.usage.input_tokens / output_tokens
        if hasattr(result, "usage") and hasattr(result.usage, "input_tokens"):
            u = result.usage
            input_t = getattr(u, "input_tokens", 0)
            output_t = getattr(u, "output_tokens", 0)
            mdl = getattr(result, "model", model)
            response_text = ""
            try:
                response_text = result.content[0].text or ""
            except Exception:
                pass
            return LLMMetadata(
                model=mdl,
                provider=provider or "anthropic",
                input_tokens=input_t,
                output_tokens=output_t,
                cost_usd=_estimate_cost(mdl, input_t, output_t),
                response_preview=response_text[:500],
            )
    except Exception:
        pass
    return None


# Very rough cost table — keeps SDK dependency-free
_COST_TABLE = {
    # (input $/1M, output $/1M)
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-haiku": (0.25, 1.25),
    "claude-sonnet-4": (3.00, 15.00),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
}

def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    for key, (inp_rate, out_rate) in _COST_TABLE.items():
        if key in model.lower():
            return (input_tokens * inp_rate + output_tokens * out_rate) / 1_000_000
    return 0.0
