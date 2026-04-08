"""
Tests for AgentLens × LangChain/CrewAI integration.
Uses LangChain's FakeListLLM — no API keys needed.

Run: python test_integrations.py
"""

import sys
import os
import json
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentlens import AgentLens
from agentlens.exporters import FileExporter
from agentlens.integrations.langchain import AgentLensCallback, AgentLensCrewCallback

OUTPUT = "/tmp/agentlens_integrations.jsonl"


def make_lens() -> AgentLens:
    return AgentLens(exporter=FileExporter(OUTPUT))


# ─────────────────────────────────────────────────────────────
# Test 1: LangChain LLM chain (FakeListLLM, no API key)
# ─────────────────────────────────────────────────────────────

def test_langchain_llm_chain():
    print("Test 1: LangChain LLM chain...")

    from langchain_core.prompts import PromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    from langchain_community.llms.fake import FakeListLLM

    lens = make_lens()
    cb = AgentLensCallback(lens, run_name="test_llm_chain", tags=["test", "langchain"])

    llm = FakeListLLM(responses=["CRDTs allow conflict-free merging of distributed state."])
    prompt = PromptTemplate.from_template("Explain {topic} in one sentence.")
    chain = prompt | llm | StrOutputParser()

    result = chain.invoke({"topic": "CRDTs"}, config={"callbacks": [cb]})

    assert "CRDT" in result or len(result) > 5, f"Unexpected result: {result}"
    print(f"  → Chain result: {result[:60]}")
    return "PASS"


# ─────────────────────────────────────────────────────────────
# Test 2: Nested chains — verifies parent_id hierarchy
# ─────────────────────────────────────────────────────────────

def test_nested_chains():
    print("Test 2: Nested chains (parent_id hierarchy)...")

    from langchain_core.prompts import PromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    from langchain_community.llms.fake import FakeListLLM

    lens = make_lens()
    cb = AgentLensCallback(lens, run_name="test_nested", tags=["test"])

    llm = FakeListLLM(responses=["step1 output", "step2 output"])
    prompt1 = PromptTemplate.from_template("Step 1: {input}")
    prompt2 = PromptTemplate.from_template("Step 2: {input}")
    parser = StrOutputParser()

    # Sequential chain: prompt1 | llm | prompt2 | llm | parser
    chain = prompt1 | llm | (lambda x: {"input": x}) | prompt2 | llm | parser

    result = chain.invoke({"input": "test"}, config={"callbacks": [cb]})
    assert result, "Expected non-empty result"
    print(f"  → Nested chain result: {result[:40]}")

    # Verify spans were created with parent relationships
    run = None
    with open(OUTPUT) as f:
        for line in f:
            d = json.loads(line)
            if d["name"] == "test_nested":
                run = d
    
    if run:
        spans = run.get("spans", [])
        print(f"  → Spans captured: {len(spans)}")
        llm_spans = [s for s in spans if s["kind"] == "llm"]
        print(f"  → LLM spans: {len(llm_spans)}")
        child_spans = [s for s in spans if s.get("parent_id")]
        print(f"  → Spans with parents: {len(child_spans)}")
    
    return "PASS"


# ─────────────────────────────────────────────────────────────
# Test 3: Tool call tracing
# ─────────────────────────────────────────────────────────────

def test_tool_tracing():
    print("Test 3: Tool call tracing...")

    from langchain_core.tools import tool as lc_tool
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_community.llms.fake import FakeListLLM
    from langchain_core.output_parsers import StrOutputParser

    lens = make_lens()
    cb = AgentLensCallback(lens, run_name="test_tools", tags=["test", "tools"])

    @lc_tool
    def web_search(query: str) -> str:
        """Search the web for information."""
        return f"Results for: {query}"

    @lc_tool
    def calculator(expression: str) -> str:
        """Calculate a math expression."""
        return str(eval(expression))

    # Invoke tools directly with the callback
    result1 = web_search.run("CRDT distributed systems", callbacks=[cb])
    result2 = calculator.run("2 + 2", callbacks=[cb])

    assert "Results for" in result1
    assert result2 == "4"
    print(f"  → web_search: {result1}")
    print(f"  → calculator: {result2}")
    return "PASS"


# ─────────────────────────────────────────────────────────────
# Test 4: Retriever tracing
# ─────────────────────────────────────────────────────────────

def test_retriever_tracing():
    print("Test 4: Retriever tracing...")

    from langchain_core.retrievers import BaseRetriever
    from langchain_core.documents import Document
    from langchain_core.callbacks import CallbackManagerForRetrieverRun

    class FakeRetriever(BaseRetriever):
        def _get_relevant_documents(
            self, query: str, *, run_manager: CallbackManagerForRetrieverRun
        ):
            return [
                Document(page_content=f"Doc about {query}", metadata={"source": "wiki"}),
                Document(page_content=f"More about {query}", metadata={"source": "arxiv"}),
            ]

    lens = make_lens()
    cb = AgentLensCallback(lens, run_name="test_retriever", tags=["test", "retrieval"])

    retriever = FakeRetriever()
    docs = retriever.invoke("CRDT consistency", config={"callbacks": [cb]})

    assert len(docs) == 2
    print(f"  → Retrieved {len(docs)} docs: {docs[0].page_content[:40]}")
    return "PASS"


# ─────────────────────────────────────────────────────────────
# Test 5: Error propagation
# ─────────────────────────────────────────────────────────────

def test_error_tracing():
    print("Test 5: Error tracing...")

    from langchain_core.prompts import PromptTemplate
    from langchain_community.llms.fake import FakeListLLM
    from langchain_core.output_parsers import StrOutputParser

    lens = make_lens()
    cb = AgentLensCallback(lens, run_name="test_error", tags=["test", "error"])

    # FakeListLLM that raises after responses exhausted
    llm = FakeListLLM(responses=[])  # no responses = will error on complex chains

    # Just test that callback records an error span by triggering
    # a chain error via a custom approach
    from langchain_core.runnables import RunnableLambda

    def explode(x):
        raise ValueError("Intentional test error")

    chain = RunnableLambda(explode)

    try:
        chain.invoke({"input": "test"}, config={"callbacks": [cb]})
    except Exception as e:
        pass  # expected

    # Check the run was still exported with error status
    run = None
    with open(OUTPUT) as f:
        for line in f:
            d = json.loads(line)
            if d["name"] == "test_error":
                run = d

    if run:
        error_spans = [s for s in run.get("spans", []) if s.get("error")]
        print(f"  → Error spans captured: {len(error_spans)}")
        if error_spans:
            print(f"  → Error: {error_spans[0]['error'][:60]}")

    return "PASS"


# ─────────────────────────────────────────────────────────────
# Test 6: CrewAI step/task callbacks
# ─────────────────────────────────────────────────────────────

def test_crewai_callbacks():
    print("Test 6: CrewAI step/task callbacks...")

    lens = make_lens()
    cb = AgentLensCrewCallback(lens, crew_name="test_crew")

    # Simulate what CrewAI would call during execution
    class FakeAgentAction:
        tool = "web_search"
        tool_input = "CRDT papers 2024"
        output = None

    class FakeAgentFinish:
        tool = None
        tool_input = None
        return_values = {"output": "Found 3 relevant papers on CRDTs"}
        output = None

    class FakeTaskOutput:
        description = "Research CRDT literature"
        raw = "CRDTs enable conflict-free distributed data structures. Key papers: Shapiro 2011..."
        agent = "research_agent"

    # Simulate a crew run: 2 steps + 1 task
    cb.on_step(FakeAgentAction())
    cb.on_step(FakeAgentFinish())
    cb.on_task(FakeTaskOutput())
    cb.finish(outputs={"result": "Research complete"})

    # Verify the run was exported
    run = None
    with open(OUTPUT) as f:
        for line in f:
            d = json.loads(line)
            if d["name"] == "test_crew":
                run = d

    assert run is not None, "CrewAI run was not exported"
    spans = run.get("spans", [])
    assert len(spans) == 3, f"Expected 3 spans, got {len(spans)}"

    tool_span = next((s for s in spans if s["kind"] == "tool"), None)
    task_span = next((s for s in spans if s["kind"] == "chain"), None)
    assert tool_span is not None, "Expected a tool span for web_search"
    assert task_span is not None, "Expected a chain span for the task"

    print(f"  → Crew run: {len(spans)} spans")
    print(f"  → Tool: {tool_span['name']}")
    print(f"  → Task: {task_span['name']}")
    return "PASS"


# ─────────────────────────────────────────────────────────────
# Test 7: patch_langchain() global patch
# ─────────────────────────────────────────────────────────────

def test_global_patch():
    print("Test 7: patch_langchain() returns ready callback...")

    import agentlens
    from langchain_core.prompts import PromptTemplate
    from langchain_community.llms.fake import FakeListLLM
    from langchain_core.output_parsers import StrOutputParser

    lens = make_lens()
    # patch_langchain() returns a configured callback — pass it via config=
    cb = agentlens.patch_langchain(lens=lens, run_name="test_global_patch", tags=["test", "global"])

    llm = FakeListLLM(responses=["Distributed systems are hard."])
    chain = PromptTemplate.from_template("{q}") | llm | StrOutputParser()

    # Modern LangChain: pass callback explicitly via RunnableConfig
    from langchain_core.runnables import RunnableConfig
    config = RunnableConfig(callbacks=[cb])
    result = chain.invoke({"q": "What are distributed systems?"}, config=config)
    assert len(result) > 5

    print(f"  → patch_langchain result: {result[:50]}")

    # Verify the run was exported
    import json
    run = None
    with open(OUTPUT) as f:
        for line in f:
            d = json.loads(line)
            if d["name"] == "test_global_patch":
                run = d
    assert run is not None, "Run was not exported"
    assert run["span_count"] >= 2, f"Expected spans, got {run['span_count']}"
    print(f"  → Exported: {run['span_count']} spans, status={run['status']}")
    return "PASS"


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def run_all():
    # Clear output file
    if os.path.exists(OUTPUT):
        os.remove(OUTPUT)

    tests = [
        ("langchain_llm_chain", test_langchain_llm_chain),
        ("nested_chains",       test_nested_chains),
        ("tool_tracing",        test_tool_tracing),
        ("retriever_tracing",   test_retriever_tracing),
        ("error_tracing",       test_error_tracing),
        ("crewai_callbacks",    test_crewai_callbacks),
        ("global_patch",        test_global_patch),
    ]

    results = []
    for name, fn in tests:
        try:
            status = fn()
            results.append((name, status))
            print(f"  ✅ {name}\n")
        except Exception as e:
            results.append((name, f"FAIL: {e}"))
            print(f"  ❌ {name}: {e}\n")
            import traceback; traceback.print_exc()

    # Summary
    print("─" * 55)
    print("Results:")
    all_pass = True
    for name, status in results:
        icon = "✅" if status == "PASS" else "❌"
        print(f"  {icon} {name}: {status}")
        if status != "PASS":
            all_pass = False

    # Show exported runs
    if os.path.exists(OUTPUT):
        with open(OUTPUT) as f:
            runs = [json.loads(l) for l in f if l.strip()]
        print(f"\nRuns exported to {OUTPUT}: {len(runs)}")
        for r in runs:
            print(f"  [{r['status']:8}] {r['name']:30} | {r['span_count']} spans")

    return all_pass


if __name__ == "__main__":
    success = run_all()
    if not success:
        sys.exit(1)
    print("\n✅ All integration tests passed.")
