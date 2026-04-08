import { useState, useEffect, useCallback } from 'react'
import { api, poll } from './lib/api'
import type { RunSummary, RunDetail, SpanSummary, DashboardStats, SpanNode } from './types'
import { RunList } from './components/RunList'
import { DagGraph } from './components/DagGraph'
import { SpanDrawer } from './components/SpanDrawer'
import { StatsBar } from './components/StatsBar'
import { DiffView } from './components/DiffView'

// ── Mock data ────────────────────────────────────────────────────────────────
function makeMockTree(): SpanNode[] {
  const now = Date.now() / 1000
  return [{
    id: 'root', run_id: 'mock-1', parent_id: null, name: 'research_agent',
    kind: 'agent', status: 'success', start_time: now-2, end_time: now,
    duration_ms: 2100, llm_model: null, llm_provider: null,
    llm_input_tokens: null, llm_output_tokens: null, llm_cost_usd: null,
    error: null, error_type: null,
    inputs: { query: 'What is CRDT?' }, outputs: { answer: 'CRDTs are...' },
    children: [
      { id: 'retrieve', run_id: 'mock-1', parent_id: 'root', name: 'retrieve_docs', kind: 'retrieval', status: 'success', start_time: now-1.8, end_time: now-1.4, duration_ms: 380, llm_model: null, llm_provider: null, llm_input_tokens: null, llm_output_tokens: null, llm_cost_usd: null, error: null, error_type: null, inputs: { query: 'What is CRDT?' }, outputs: { docs: ['doc_0','doc_1','doc_2'] }, children: [] },
      { id: 'rerank', run_id: 'mock-1', parent_id: 'root', name: 'rerank_results', kind: 'chain', status: 'success', start_time: now-1.3, end_time: now-1.1, duration_ms: 200, llm_model: null, llm_provider: null, llm_input_tokens: null, llm_output_tokens: null, llm_cost_usd: null, error: null, error_type: null, inputs: {}, outputs: {}, children: [] },
      { id: 'llm-1', run_id: 'mock-1', parent_id: 'root', name: 'chat_completion', kind: 'llm', status: 'success', start_time: now-1.0, end_time: now-0.3, duration_ms: 700, llm_model: 'gpt-4o-mini', llm_provider: 'openai', llm_input_tokens: 350, llm_output_tokens: 120, llm_cost_usd: 0.000125, error: null, error_type: null, inputs: { prompt: 'Summarize docs...' }, outputs: { text: 'CRDTs are...' }, children: [] },
      { id: 'fmt', run_id: 'mock-1', parent_id: 'root', name: 'format_answer', kind: 'tool', status: 'error', start_time: now-0.2, end_time: now-0.1, duration_ms: 95, llm_model: null, llm_provider: null, llm_input_tokens: null, llm_output_tokens: null, llm_cost_usd: null, error: 'KeyError: missing field "citations"', error_type: 'KeyError', inputs: { format: 'markdown' }, outputs: {}, children: [] },
    ],
  }]
}

const MOCK_RUNS: RunSummary[] = [
  { id: 'mock-1', name: 'research_agent', status: 'success', start_time: Date.now()/1000-120, end_time: Date.now()/1000-118, duration_ms: 2100, span_count: 5, total_tokens: 470, total_cost_usd: 0.000125, tags: ['rag','prod'], tokens_exceeded: false, cost_exceeded: false },
  { id: 'mock-2', name: 'research_agent', status: 'error', start_time: Date.now()/1000-400, end_time: Date.now()/1000-398, duration_ms: 4200, span_count: 4, total_tokens: 680, total_cost_usd: 0.00045, tags: ['rag','debug'], tokens_exceeded: false, cost_exceeded: false },
  { id: 'mock-3', name: 'summary_agent', status: 'success', start_time: Date.now()/1000-900, end_time: Date.now()/1000-897, duration_ms: 3400, span_count: 7, total_tokens: 1200, total_cost_usd: 0.00078, tags: ['summarize'], tokens_exceeded: false, cost_exceeded: false },
  { id: 'mock-4', name: 'research_agent', status: 'success', start_time: Date.now()/1000-3600, end_time: Date.now()/1000-3598, duration_ms: 1950, span_count: 5, total_tokens: 510, total_cost_usd: 0.000138, tags: ['rag','prod'], tokens_exceeded: false, cost_exceeded: false },
]

const MOCK_STATS: DashboardStats = { total_runs: 142, success_runs: 134, error_runs: 8, total_tokens: 284500, total_cost_usd: 0.4821, avg_duration_ms: 1840 }

const MOCK_DIFF = {
  run_a: MOCK_RUNS[0],
  run_b: MOCK_RUNS[1],
  span_diffs: [
    { name: 'research_agent', kind: 'agent' as const, only_in: null, duration_ms_a: 2100, duration_ms_b: 4200, duration_delta_ms: 2100, status_a: 'success' as const, status_b: 'error' as const, status_changed: true, tokens_a: 470, tokens_b: 680 },
    { name: 'retrieve_docs', kind: 'retrieval' as const, only_in: null, duration_ms_a: 380, duration_ms_b: 390, duration_delta_ms: 10, status_a: 'success' as const, status_b: 'success' as const, status_changed: false, tokens_a: null, tokens_b: null },
    { name: 'rerank_results', kind: 'chain' as const, only_in: null, duration_ms_a: 200, duration_ms_b: 180, duration_delta_ms: -20, status_a: 'success' as const, status_b: 'success' as const, status_changed: false, tokens_a: null, tokens_b: null },
    { name: 'chat_completion', kind: 'llm' as const, only_in: null, duration_ms_a: 700, duration_ms_b: 3200, duration_delta_ms: 2500, status_a: 'success' as const, status_b: 'error' as const, status_changed: true, tokens_a: 470, tokens_b: 680 },
    { name: 'format_answer', kind: 'tool' as const, only_in: null, duration_ms_a: 95, duration_ms_b: 88, duration_delta_ms: -7, status_a: 'error' as const, status_b: 'success' as const, status_changed: true, tokens_a: null, tokens_b: null },
    { name: 'validate_output', kind: 'tool' as const, only_in: 'b' as const, duration_ms_a: null, duration_ms_b: 120, duration_delta_ms: null, status_a: null, status_b: 'error' as const, status_changed: false, tokens_a: null, tokens_b: null },
  ],
  total_duration_delta_ms: 2100,
  total_tokens_delta: 210,
  total_cost_delta_usd: 0.000325,
}

// ── App ──────────────────────────────────────────────────────────────────────
const DEMO_MODE = !import.meta.env.VITE_API_URL

export default function App() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [selectedRun, setSelectedRun] = useState<RunDetail | null>(null)
  const [selectedSpan, setSelectedSpan] = useState<SpanSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [nameFilter, setNameFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [diffIds, setDiffIds] = useState<[string, string] | null>(null)

  const loadRuns = useCallback(async () => {
    if (DEMO_MODE) { setRuns(MOCK_RUNS); setTotal(MOCK_RUNS.length); setStats(MOCK_STATS); return }
    setLoading(true)
    try {
      const [r, s] = await Promise.all([
        api.runs.list({ name: nameFilter, status: statusFilter, limit: 50 }),
        api.analytics.stats(),
      ])
      setRuns(r.runs); setTotal(r.total); setStats(s)
    } catch(e) { console.error(e) } finally { setLoading(false) }
  }, [nameFilter, statusFilter])

  useEffect(() => { return poll(loadRuns, 5000) }, [loadRuns])

  const selectRun = useCallback(async (id: string) => {
    setSelectedSpan(null); setDiffIds(null)
    if (DEMO_MODE) {
      const m = MOCK_RUNS.find(r => r.id === id)!
      setSelectedRun({ ...m, metadata: {}, budget: { max_total_tokens: 2000, max_cost_usd: 0.01, tokens_used: m.total_tokens, cost_used: m.total_cost_usd, tokens_exceeded: false, cost_exceeded: false }, spans: [], span_tree: makeMockTree() })
      return
    }
    try { setSelectedRun(await api.runs.get(id)) } catch(e) { console.error(e) }
  }, [])

  const startDiff = useCallback((ids: [string, string]) => {
    setSelectedRun(null); setSelectedSpan(null)
    setDiffIds(ids)
  }, [])

  const diffRunA = diffIds ? runs.find(r => r.id === diffIds[0]) ?? null : null
  const diffRunB = diffIds ? runs.find(r => r.id === diffIds[1]) ?? null : null

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100vh', background:'#020617', color:'#e2e8f0', overflow:'hidden' }}>
      <StatsBar stats={stats} />

      {DEMO_MODE && (
        <div style={{ background:'rgba(99,102,241,0.12)', borderBottom:'1px solid rgba(99,102,241,0.25)', padding:'5px 20px', fontSize:11, color:'#818cf8', textAlign:'center', fontFamily:'ui-sans-serif,sans-serif' }}>
          ⚡ Demo mode — try selecting two runs with the <strong>⇄</strong> compare button, or set <code style={{background:'rgba(255,255,255,0.08)',padding:'1px 4px',borderRadius:3}}>VITE_API_URL=http://localhost:7430</code> to connect live
        </div>
      )}

      <div style={{ display:'flex', flex:1, overflow:'hidden' }}>
        <RunList
          runs={runs} total={total}
          selectedId={selectedRun?.id ?? null}
          diffIds={diffIds}
          onSelect={selectRun}
          onSearch={setNameFilter}
          onFilterStatus={setStatusFilter}
          onRefresh={loadRuns}
          onStartDiff={startDiff}
          loading={loading}
        />

        <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden', position:'relative' }}>
          {/* Diff view overlay */}
          {diffIds && diffRunA && diffRunB && (
            DEMO_MODE
              ? <MockDiffView runA={diffRunA} runB={diffRunB} onClose={() => setDiffIds(null)} />
              : <DiffView runA={diffRunA} runB={diffRunB} onClose={() => setDiffIds(null)} />
          )}

          {/* Normal trace view */}
          {selectedRun && !diffIds && (
            <>
              <div style={{ padding:'9px 18px', borderBottom:'1px solid #1e293b', display:'flex', alignItems:'center', gap:14, background:'#0f172a', fontFamily:'ui-sans-serif,sans-serif', flexShrink:0 }}>
                <span style={{ fontSize:13, fontWeight:700, color:'#f1f5f9', fontFamily:'ui-monospace,monospace' }}>{selectedRun.name}</span>
                <span style={{ fontSize:10, color:'#334155' }}>{selectedRun.id.slice(0,8)}</span>
                {selectedRun.tags.map(t => (
                  <span key={t} style={{ fontSize:9, padding:'2px 7px', borderRadius:4, background:'#1e3a5f', color:'#60a5fa', fontWeight:600 }}>{t}</span>
                ))}
                <div style={{ marginLeft:'auto', fontSize:11, color:'#475569' }}>
                  {selectedRun.span_count} spans · {selectedRun.total_tokens.toLocaleString()} tokens · click any node for details
                </div>
              </div>
              <div style={{ flex:1, position:'relative', overflow:'hidden' }}>
                <DagGraph spanTree={selectedRun.span_tree} onSelectSpan={setSelectedSpan} selectedSpanId={selectedSpan?.id} />
                <SpanDrawer span={selectedSpan} onClose={() => setSelectedSpan(null)} />
              </div>
            </>
          )}

          {/* Empty state */}
          {!selectedRun && !diffIds && <EmptyState />}
        </div>
      </div>

      <style>{`@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}*{box-sizing:border-box}body{margin:0}::-webkit-scrollbar{width:5px}::-webkit-scrollbar-track{background:#0f172a}::-webkit-scrollbar-thumb{background:#1e293b;border-radius:3px}input{outline:none}`}</style>
    </div>
  )
}

// Mock diff injects mock data so DiffView works without a server
function MockDiffView({ runA, runB, onClose }: { runA: RunSummary; runB: RunSummary; onClose: () => void }) {
  useEffect(() => {
    const orig = api.runs.diff
    api.runs.diff = async () => MOCK_DIFF as any
    return () => { api.runs.diff = orig }
  }, [])
  return <DiffView runA={runA} runB={runB} onClose={onClose} />
}

function EmptyState() {
  return (
    <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', flexDirection:'column', gap:10, color:'#334155', fontFamily:'ui-sans-serif,sans-serif' }}>
      <div style={{ fontSize:44 }}>🔭</div>
      <div style={{ fontSize:15, fontWeight:700, color:'#475569' }}>Select a run to view its trace</div>
      <div style={{ fontSize:12, color:'#334155', textAlign:'center', lineHeight:1.6 }}>
        Click any run in the sidebar to see the agent DAG.<br/>
        Use <span style={{color:'#6366f1'}}>⇄</span> to compare two runs side-by-side.
      </div>
    </div>
  )
}
