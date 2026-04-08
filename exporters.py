"""
Exporters for AgentLens.
Responsible for sending completed AgentRuns to a backend.

Pluggable: swap HttpExporter for a file, queue, or custom sink.
"""

from __future__ import annotations
import json
import logging
import threading
import queue
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import AgentRun

logger = logging.getLogger("agentlens.exporter")


class BaseExporter(ABC):
    @abstractmethod
    def export(self, run: "AgentRun") -> None:
        """Called after a run completes. Must be non-blocking or fast."""
        ...

    def shutdown(self):
        pass


class NoopExporter(BaseExporter):
    """Does nothing. Useful in tests."""
    def export(self, run):
        pass


class ConsoleExporter(BaseExporter):
    """Prints a summary to stdout. Great for local dev."""

    def export(self, run: "AgentRun"):
        d = run.to_dict()
        print(f"\n{'='*60}")
        print(f"[AgentLens] Run: {d['name']}  id={d['id'][:8]}")
        print(f"  Status : {d['status']}")
        print(f"  Duration: {(d['duration_ms'] or 0):.0f}ms")
        print(f"  Spans   : {d['span_count']}")
        print(f"  Tokens  : {d['total_tokens']}  Cost: ${d['total_cost_usd']:.5f}")
        budget = d["budget"]
        if budget["tokens_exceeded"]:
            print(f"  ⚠️  TOKEN BUDGET EXCEEDED ({budget['tokens_used']} > {budget['max_total_tokens']})")
        if budget["cost_exceeded"]:
            print(f"  ⚠️  COST BUDGET EXCEEDED (${budget['cost_used']:.5f} > ${budget['max_cost_usd']:.5f})")
        print(f"{'='*60}\n")


class HttpExporter(BaseExporter):
    """
    Ships runs to the AgentLens server over HTTP.
    Uses a background thread + queue so it never blocks the agent.
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:7430",
        api_key: str = "",
        timeout: float = 5.0,
        max_queue: int = 1000,
    ):
        self.endpoint = endpoint.rstrip("/") + "/api/ingest/run"
        self.api_key = api_key
        self.timeout = timeout
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue)
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def export(self, run: "AgentRun"):
        try:
            self._queue.put_nowait(run.to_dict())
        except queue.Full:
            logger.warning("AgentLens export queue full — dropping run %s", run.id)

    def _worker(self):
        import urllib.request
        import urllib.error

        while True:
            payload = self._queue.get()
            if payload is None:
                break
            try:
                body = json.dumps(payload).encode()
                req = urllib.request.Request(
                    self.endpoint,
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-API-Key": self.api_key,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout):
                    pass
            except Exception as e:
                logger.warning("AgentLens export failed: %s", e)
            finally:
                self._queue.task_done()

    def shutdown(self):
        self._queue.put(None)
        self._thread.join(timeout=5)


class FileExporter(BaseExporter):
    """
    Appends each run as a JSON line to a file.
    Useful for offline replay or CI pipelines.
    """

    def __init__(self, path: str = "agentlens_runs.jsonl"):
        self.path = path
        self._lock = threading.Lock()

    def export(self, run: "AgentRun"):
        with self._lock:
            with open(self.path, "a") as f:
                f.write(json.dumps(run.to_dict()) + "\n")
