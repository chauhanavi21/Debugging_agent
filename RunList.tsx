import { useState } from 'react'
import { Search, RefreshCw, AlertCircle, CheckCircle, Clock, GitCompare } from 'lucide-react'
import type { RunSummary } from '../types'
import { STATUS_COLOR, fmtDuration, fmtTokens, fmtCost, timeAgo } from '../lib/styles'

interface Props {
  runs: RunSummary[]
  total: number
  selectedId: string | null
  diffIds: [string, string] | null
  onSelect: (id: string) => void
  onSearch: (q: string) => void
  onFilterStatus: (s: string) => void
  onRefresh: () => void
  onStartDiff: (ids: [string, string]) => void
  loading: boolean
}

export function RunList({
  runs, total, selectedId, diffIds,
  onSelect, onSearch, onFilterStatus, onRefresh, onStartDiff, loading,
}: Props) {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [compareMode, setCompareMode] = useState(false)
  const [compareA, setCompareA] = useState<string | null>(null)

  function handleSearch(v: string) { setSearch(v); onSearch(v) }
  function handleStatus(v: string) {
    const next = v === status ? '' : v
    setStatus(next); onFilterStatus(next)
  }

  function handleRowClick(id: string) {
    if (!compareMode) { onSelect(id); return }
    if (!compareA) { setCompareA(id); return }
    if (compareA === id) { setCompareA(null); return }
    onStartDiff([compareA, id])
    setCompareMode(false); setCompareA(null)
  }

  function toggleCompare() {
    setCompareMode(v => !v)
    setCompareA(null)
  }

  const StatusBtn = ({ s, icon }: { s: string; icon: React.ReactNode }) => (
    <button onClick={() => handleStatus(s)} style={{
      display: 'flex', alignItems: 'center', gap: 4,
      padding: '4px 8px', borderRadius: 6,
      border: `1px solid ${status === s ? STATUS_COLOR[s as keyof typeof STATUS_COLOR] : '#334155'}`,
      background: status === s ? STATUS_COLOR[s as keyof typeof STATUS_COLOR] + '22' : 'transparent',
      color: status === s ? STATUS_COLOR[s as keyof typeof STATUS_COLOR] : '#64748b',
      fontSize: 10, fontWeight: 600, cursor: 'pointer',
      textTransform: 'uppercase', letterSpacing: '0.05em',
    }}>{icon} {s}</button>
  )

  return (
    <div style={{
      width: 300, minWidth: 300,
      background: '#0f172a', borderRight: '1px solid #1e293b',
      display: 'flex', flexDirection: 'column',
      fontFamily: 'ui-sans-serif, sans-serif',
    }}>
      {/* Header */}
      <div style={{ padding: '14px 14px 10px', borderBottom: '1px solid #1e293b' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800, color: '#f1f5f9', letterSpacing: '-0.02em' }}>AgentLens</div>
            <div style={{ fontSize: 11, color: '#475569' }}>{total} run{total !== 1 ? 's' : ''}</div>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={toggleCompare} title="Compare two runs" style={{
              background: compareMode ? 'rgba(99,102,241,0.2)' : 'none',
              border: `1px solid ${compareMode ? '#6366f1' : '#334155'}`,
              borderRadius: 6, cursor: 'pointer',
              color: compareMode ? '#818cf8' : '#64748b',
              padding: 6, display: 'flex', alignItems: 'center',
            }}>
              <GitCompare size={14} />
            </button>
            <button onClick={onRefresh} style={{
              background: 'none', border: '1px solid #334155',
              borderRadius: 6, cursor: 'pointer',
              color: loading ? '#6366f1' : '#64748b',
              padding: 6, display: 'flex', alignItems: 'center',
            }}>
              <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            </button>
          </div>
        </div>

        {/* Compare mode hint */}
        {compareMode && (
          <div style={{
            padding: '6px 10px', borderRadius: 6, marginBottom: 8,
            background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.3)',
            fontSize: 11, color: '#a5b4fc', lineHeight: 1.4,
          }}>
            {!compareA
              ? '① Click first run to compare'
              : '② Click second run to diff'}
          </div>
        )}

        {/* Search */}
        <div style={{ position: 'relative', marginBottom: 8 }}>
          <Search size={12} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: '#475569' }} />
          <input value={search} onChange={e => handleSearch(e.target.value)} placeholder="Search runs…" style={{
            width: '100%', boxSizing: 'border-box',
            padding: '6px 8px 6px 26px',
            background: '#1e293b', border: '1px solid #334155',
            borderRadius: 6, color: '#e2e8f0', fontSize: 12, outline: 'none',
          }} />
        </div>

        {/* Status filters */}
        <div style={{ display: 'flex', gap: 5 }}>
          <StatusBtn s="success" icon={<CheckCircle size={9} />} />
          <StatusBtn s="error" icon={<AlertCircle size={9} />} />
          <StatusBtn s="running" icon={<Clock size={9} />} />
        </div>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {runs.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#475569', fontSize: 12 }}>
            No runs yet.<br />
            <span style={{ fontSize: 11 }}>Instrument your agent with the SDK.</span>
          </div>
        ) : runs.map(run => (
          <RunRow
            key={run.id}
            run={run}
            selected={run.id === selectedId}
            compareA={run.id === compareA}
            inDiff={diffIds ? (diffIds[0] === run.id || diffIds[1] === run.id) : false}
            compareMode={compareMode}
            onClick={() => handleRowClick(run.id)}
          />
        ))}
      </div>
    </div>
  )
}

function RunRow({ run, selected, compareA, inDiff, compareMode, onClick }: {
  run: RunSummary; selected: boolean; compareA: boolean
  inDiff: boolean; compareMode: boolean; onClick: () => void
}) {
  const sc = STATUS_COLOR[run.status]
  const isHighlit = compareA || inDiff
  const borderColor = compareA ? '#6366f1' : inDiff ? '#06b6d4' : selected ? '#6366f1' : 'transparent'

  return (
    <div onClick={onClick} style={{
      padding: '10px 14px',
      borderBottom: '1px solid #0f172a',
      background: isHighlit ? '#1a2744' : selected ? '#1e293b' : 'transparent',
      borderLeft: `3px solid ${borderColor}`,
      cursor: 'pointer',
      position: 'relative',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 3 }}>
        <div style={{
          fontSize: 12, fontWeight: 600, color: '#f1f5f9',
          fontFamily: 'ui-monospace, monospace',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 155,
        }}>{run.name}</div>
        <div style={{ fontSize: 10, fontWeight: 700, color: sc, textTransform: 'uppercase' }}>
          {run.status}{(run.tokens_exceeded || run.cost_exceeded) ? ' ⚠' : ''}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, fontSize: 11, color: '#64748b', marginBottom: 4 }}>
        <span>{fmtDuration(run.duration_ms)}</span>
        <span>·</span>
        <span>{run.span_count} spans</span>
        <span>·</span>
        <span>{fmtTokens(run.total_tokens)}</span>
        {run.total_cost_usd > 0 && <><span>·</span><span style={{ color: '#f59e0b' }}>{fmtCost(run.total_cost_usd)}</span></>}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', gap: 3 }}>
          {run.tags.slice(0, 3).map(tag => (
            <span key={tag} style={{
              fontSize: 9, padding: '1px 5px', borderRadius: 3,
              background: '#1e3a5f', color: '#60a5fa', fontWeight: 600,
            }}>{tag}</span>
          ))}
        </div>
        <div style={{ fontSize: 10, color: '#334155' }}>{timeAgo(run.start_time)}</div>
      </div>

      {compareMode && compareA && (
        <div style={{
          position: 'absolute', top: 6, right: 8,
          fontSize: 9, fontWeight: 800, color: '#6366f1',
          background: 'rgba(99,102,241,0.2)', borderRadius: 3, padding: '1px 5px',
        }}>A</div>
      )}
    </div>
  )
}
