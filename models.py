"""
Core data models for AgentLens spans and runs.
Designed to be OTel-compatible but agent-aware.
"""

from __future__ import annotations
import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Optional


class SpanStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


class SpanKind(str, Enum):
    AGENT = "agent"       # top-level agent entry
    TOOL = "tool"         # tool/function call
    LLM = "llm"           # raw LLM call
    CHAIN = "chain"       # sub-chain or sub-agent
    RETRIEVAL = "retrieval"  # RAG retrieval step
    CUSTOM = "custom"


@dataclass
class LLMMetadata:
    """Captured metadata for LLM calls within a span."""
    model: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    prompt_preview: str = ""      # first 500 chars of prompt
    response_preview: str = ""    # first 500 chars of response
    temperature: Optional[float] = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class Span:
    """
    A single unit of work within an agent run.
    Can be nested — a Span can have child Spans.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str = ""
    parent_id: Optional[str] = None          # None = root span
    name: str = ""
    kind: SpanKind = SpanKind.CUSTOM
    status: SpanStatus = SpanStatus.RUNNING

    # Timing
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    # Payload
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_type: Optional[str] = None

    # LLM-specific (populated when kind == LLM)
    llm: Optional[LLMMetadata] = None

    # Budget tracking
    token_budget: Optional[int] = None
    cost_budget_usd: Optional[float] = None

    @property
    def duration_ms(self) -> Optional[float]:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000

    def finish(self, outputs: dict[str, Any] = None, error: Exception = None):
        self.end_time = time.time()
        if error:
            self.status = SpanStatus.ERROR
            self.error = str(error)
            self.error_type = type(error).__name__
        else:
            self.status = SpanStatus.SUCCESS
            if outputs:
                self.outputs = outputs

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "kind": self.kind.value,
            "status": self.status.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "attributes": self.attributes,
            "error": self.error,
            "error_type": self.error_type,
            "llm": {
                "model": self.llm.model,
                "provider": self.llm.provider,
                "input_tokens": self.llm.input_tokens,
                "output_tokens": self.llm.output_tokens,
                "total_tokens": self.llm.total_tokens,
                "cost_usd": self.llm.cost_usd,
                "prompt_preview": self.llm.prompt_preview,
                "response_preview": self.llm.response_preview,
                "temperature": self.llm.temperature,
            } if self.llm else None,
        }


@dataclass
class AgentRun:
    """
    A complete agent execution session.
    Contains the full tree of Spans.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.RUNNING

    spans: list[Span] = field(default_factory=list)

    # Budget config (optional)
    max_total_tokens: Optional[int] = None
    max_cost_usd: Optional[float] = None

    @property
    def duration_ms(self) -> Optional[float]:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000

    @property
    def total_tokens(self) -> int:
        return sum(
            s.llm.total_tokens for s in self.spans
            if s.llm is not None
        )

    @property
    def total_cost_usd(self) -> float:
        return sum(
            s.llm.cost_usd for s in self.spans
            if s.llm is not None
        )

    @property
    def root_span(self) -> Optional[Span]:
        return next((s for s in self.spans if s.parent_id is None), None)

    def get_span_tree(self) -> dict:
        """Build nested tree structure from flat span list."""
        span_map = {s.id: {**s.to_dict(), "children": []} for s in self.spans}
        roots = []
        for span_data in span_map.values():
            pid = span_data["parent_id"]
            if pid and pid in span_map:
                span_map[pid]["children"].append(span_data)
            else:
                roots.append(span_data)
        return roots

    def finish(self, error: Exception = None):
        self.end_time = time.time()
        self.status = SpanStatus.ERROR if error else SpanStatus.SUCCESS

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "tags": self.tags,
            "metadata": self.metadata,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "span_count": len(self.spans),
            "spans": [s.to_dict() for s in self.spans],
            "span_tree": self.get_span_tree(),
            "budget": {
                "max_total_tokens": self.max_total_tokens,
                "max_cost_usd": self.max_cost_usd,
                "tokens_used": self.total_tokens,
                "cost_used": self.total_cost_usd,
                "tokens_exceeded": (
                    self.max_total_tokens is not None
                    and self.total_tokens > self.max_total_tokens
                ),
                "cost_exceeded": (
                    self.max_cost_usd is not None
                    and self.total_cost_usd > self.max_cost_usd
                ),
            },
        }
