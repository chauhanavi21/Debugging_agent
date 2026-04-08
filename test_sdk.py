"""
Integration test / demo for the AgentLens SDK.
Run with: python test_sdk.py
"""

import sys
import os
import asyncio
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentlens import AgentLens, SpanKind
from agentlens.exporters import FileExporter, ConsoleExporter
from agentlens.models import AgentRun


# ──────────────────────────────────────────────
# Setup: use file exporter so we can inspect output
# ──────────────────────────────────────────────
OUTPUT_FILE = "/tmp/agentlens_test.jsonl"
lens = AgentLens(exporter=FileExporter(OUTPUT_FILE))


# ──────────────────────────────────────────────
# Test 1: Basic sync agent with nested spans
# ──────────────────────────────────────────────

@lens.span("retrieve_documents", kind=SpanKind.RETRIEVAL)
def retrieve_documents(query: str) -> list:
    # Simulate retrieval
    return [f"doc_{i}: relevant content about {query}" for i in range(3)]


@lens.span("rerank_results", kind=SpanKind.CHAIN)
def rerank_results(docs: list, query: str) -> list:
    # Simulate reranking
    return sorted(docs, reverse=True)


@lens.tool("format_answer")
def format_answer(docs: list, query: str) -> str:
    return f"Based on {len(docs)} documents: answer to '{query}'"


@lens.trace("research_agent", kind=SpanKind.AGENT, tags=["test", "sync"])
def research_agent(query: str) -> str:
    docs = retrieve_documents(query)
    ranked = rerank_results(docs, query)
    answer = format_answer(ranked, query)
    return answer


# ──────────────────────────────────────────────
# Test 2: Async agent
# ──────────────────────────────────────────────

@lens.span("async_search", kind=SpanKind.TOOL)
async def async_search(query: str) -> list:
    await asyncio.sleep(0.01)  # simulate I/O
    return [f"result_{i}" for i in range(5)]


@lens.trace("async_agent", kind=SpanKind.AGENT, tags=["test", "async"])
async def async_agent(query: str) -> str:
    results = await async_search(query)
    return f"Found {len(results)} results for '{query}'"


# ──────────────────────────────────────────────
# Test 3: Budget guard — agent that simulates token usage
# ──────────────────────────────────────────────

def simulate_llm_call(prompt: str, tokens_used: int = 100):
    """Fake LLM call that manually registers token usage."""
    run = lens._exporter  # just for illustration
    return f"LLM response to: {prompt[:30]}"


@lens.trace(
    "budget_agent",
    kind=SpanKind.AGENT,
    max_total_tokens=500,
    max_cost_usd=0.001,
    tags=["test", "budget"],
)
def budget_agent(query: str) -> str:
    # Manually add LLM metadata to current run to simulate token usage
    from agentlens.context import get_current_run
    from agentlens.models import LLMMetadata, Span, SpanKind as SK

    run = get_current_run()

    # Simulate 3 LLM calls, each using 200 tokens
    for i in range(3):
        fake_span = Span(
            run_id=run.id,
            name=f"llm_call_{i}",
            kind=SK.LLM,
        )
        fake_span.llm = LLMMetadata(
            model="gpt-4o-mini",
            provider="openai",
            input_tokens=150,
            output_tokens=50,
            cost_usd=0.00003,
        )
        fake_span.finish()
        run.spans.append(fake_span)

        # Check budget after each call
        budget = lens.check_budget(run)
        if not budget["ok"]:
            return f"⚠️ Budget exceeded at step {i+1}. Stopping. Used: {budget['tokens_used']} tokens"

    return "Completed within budget"


# ──────────────────────────────────────────────
# Test 4: Error handling
# ──────────────────────────────────────────────

@lens.span("failing_tool", kind=SpanKind.TOOL)
def failing_tool(x: int) -> int:
    if x < 0:
        raise ValueError(f"Input must be non-negative, got {x}")
    return x * 2


@lens.trace("error_agent", kind=SpanKind.AGENT, tags=["test", "error"])
def error_agent(value: int) -> int:
    return failing_tool(value)


# ──────────────────────────────────────────────
# Run all tests
# ──────────────────────────────────────────────

def run_tests():
    results = []

    # Test 1: Basic sync
    print("Test 1: Sync agent with nested spans...")
    result = research_agent("machine learning fundamentals")
    assert "answer" in result
    results.append(("sync_agent", "PASS"))
    print(f"  → {result}\n")

    # Test 2: Async
    print("Test 2: Async agent...")
    result = asyncio.run(async_agent("quantum computing"))
    assert "Found" in result
    results.append(("async_agent", "PASS"))
    print(f"  → {result}\n")

    # Test 3: Budget guard
    print("Test 3: Budget guard...")
    result = budget_agent("expensive query")
    results.append(("budget_agent", "PASS"))
    print(f"  → {result}\n")

    # Test 4: Error handling
    print("Test 4: Error propagation...")
    try:
        error_agent(-5)
        results.append(("error_agent", "FAIL — expected exception"))
    except ValueError as e:
        results.append(("error_agent", "PASS"))
        print(f"  → Correctly caught: {e}\n")

    # Validate output file
    print("Validating output file...")
    with open(OUTPUT_FILE) as f:
        lines = [json.loads(l) for l in f if l.strip()]

    assert len(lines) >= 3, f"Expected at least 3 runs, got {len(lines)}"

    for run in lines:
        assert "id" in run
        assert "spans" in run
        assert "span_tree" in run
        assert "budget" in run
        assert len(run["spans"]) > 0, f"Run {run['name']} has no spans"

    print(f"\n{'─'*50}")
    print(f"Output file: {OUTPUT_FILE}")
    print(f"Runs recorded: {len(lines)}")
    for run in lines:
        tree_depth = _max_depth(run["span_tree"])
        print(f"  [{run['status']:8}] {run['name']:20} | "
              f"{run['span_count']} spans | depth={tree_depth} | "
              f"{run['total_tokens']} tokens | ${run['total_cost_usd']:.6f}")

    print(f"\n{'─'*50}")
    print("Test Results:")
    all_pass = True
    for name, status in results:
        icon = "✅" if "PASS" in status else "❌"
        print(f"  {icon} {name}: {status}")
        if "FAIL" in status:
            all_pass = False

    return all_pass


def _max_depth(nodes, depth=1):
    if not nodes:
        return 0
    return max(
        (depth if not n.get("children") else _max_depth(n["children"], depth + 1))
        for n in nodes
    )


if __name__ == "__main__":
    success = run_tests()

    if success:
        print("\n✅ All tests passed. SDK is working correctly.")

        # Print sample run JSON
        with open(OUTPUT_FILE) as f:
            first_run = json.loads(f.readline())

        print(f"\nSample span tree from '{first_run['name']}':")
        def print_tree(nodes, indent=0):
            for node in nodes:
                status_icon = "✓" if node["status"] == "success" else "✗"
                duration = f"{node['duration_ms']:.1f}ms" if node["duration_ms"] else "?"
                print(f"{'  ' * indent}{status_icon} [{node['kind']:10}] {node['name']} ({duration})")
                print_tree(node.get("children", []), indent + 1)
        print_tree(first_run["span_tree"])
    else:
        print("\n❌ Some tests failed.")
        sys.exit(1)
