"""
Context management for AgentLens.
Uses contextvars (Python 3.7+) so it works correctly
across async code, threads, and concurrent agent runs.
"""

from __future__ import annotations
from contextvars import ContextVar
from typing import Optional

from .models import AgentRun, Span

# Each async task / thread gets its own context
_current_run: ContextVar[Optional[AgentRun]] = ContextVar("_current_run", default=None)
_current_span: ContextVar[Optional[Span]] = ContextVar("_current_span", default=None)


def get_current_run() -> Optional[AgentRun]:
    return _current_run.get()


def get_current_span() -> Optional[Span]:
    return _current_span.get()


def set_current_run(run: Optional[AgentRun]):
    return _current_run.set(run)


def set_current_span(span: Optional[Span]):
    return _current_span.set(span)


# Public API
def current_run() -> Optional[AgentRun]:
    """Returns the AgentRun active in this context, if any."""
    return get_current_run()


def current_span() -> Optional[Span]:
    """Returns the Span active in this context, if any."""
    return get_current_span()
