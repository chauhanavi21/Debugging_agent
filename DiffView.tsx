import { useState, useEffect } from 'react'
import { ArrowRight, TrendingUp, TrendingDown, Minus, AlertCircle, CheckCircle } from 'lucide-react'
import type { RunSummary, DiffResponse, SpanDiff } from '../types'
import { api } from '../lib/api'
import { KIND_COLOR, STATUS_COLOR, fmtDuration, fmtCost, fmtTokens } from '../lib/styles'

interface Props {
  runA: RunSummary
  runB: RunSummary
  onClose: () => void
}

export function DiffView({ runA, runB, onClose }: Props) {
  const [diff, setDiff] = useState<DiffResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    api.runs.diff(runA.id, runB.id)
      .then(setDiff)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [runA.id, runB.id])

  return (
    <div style={{
      position: 'absolute', inset: 0,
      background: '#0f172a',
      display: 'flex', flexDirection: 'column',
      fontFamily: 'ui-sans-serif, sans-serif',
      zIndex: 20,
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 20px',
        borderBottom: '1px solid #1e293b',
        display: 'flex', alignItems: 'center', gap: 16,
        background: '#020617',
      }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: '#6366f1', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          Run Diff
        </div>

        <RunChip run={runA} label="A" color="#6366f1" />
        <ArrowRight size={14} color="#334155" />
        <RunChip run={runB} label="B" color="#06b6d4" />

        {diff && (
          <div style={{ display: 'flex', gap: 20, marginLeft: 8 }}>
            <DeltaChip
              label="Duration"
              delta={diff.total_duration_delta_ms}
              format={v => fmtDuration(Math.abs(v))}
            />
            <DeltaChip
              label="Tokens"
              delta={diff.total_tokens_delta}
              format={v => fmtTokens(Math.abs(v))}
            />
            <DeltaChip
              label="Cost"
              delta={diff.total_cost_delta_usd}
              format={v => fmtCost(Math.abs(v))}
            />
          </div>
        )}

        <button
          onClick={onClose}
          style={{
            marginLeft: 'auto', background: 'none',
            border: '1px solid #334155', borderRadius: 6,
            color: '#64748b', padding: '5px 14px', cursor: 'pointer',
            fontSize: 12, fontWeight: 600,
          }}
        >
          ✕ Close
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
        {loading && (
          <div style={{ textAlign: 'center', color: '#475569', paddingTop: 60, fontSize: 14 }}>
            Comparing runs…
          </div>
        )}
        {error && (
          <div style={{
            padding: 16, borderRadius: 8,
            background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)',
            color: '#fca5a5', fontSize: 13,
          }}>
            Failed to load diff: {error}
          </div>
        )}
        {diff && !loading && (
          <>
            {/* Summary cards */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
              <RunCard run={diff.run_a} label="A" color="#6366f1" />
              <RunCard run={diff.run_b} label="B" color="#06b6d4" />
            </div>

            {/* Span diff table */}
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 12 }}>
                Span-by-Span Comparison — {diff.span_diffs.length} spans
              </div>

              {/* Table header */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: '200px 80px 110px 110px 100px 80px 80px',
                padding: '7px 12px', gap: 8,
                background: '#0f172a',
                borderRadius: '6px 6px 0 0',
                border: '1px solid #1e293b',
                fontSize: 10, fontWeight: 700, color: '#475569',
                textTransform: 'uppercase', letterSpacing: '0.07em',
              }}>
                <div>Span</div>
                <div>Kind</div>
                <div>Duration A</div>
                <div>Duration B</div>
                <div>Δ Duration</div>
                <div>Status A</div>
                <div>Status B</div>
              </div>

              {/* Rows */}
              {diff.span_diffs.map((d, i) => (
                <SpanDiffRow key={i} diff={d} />
              ))}
            </div>

            {/* Legend */}
            <div style={{ display: 'flex', gap: 20, marginTop: 20, fontSize: 11, color: '#475569' }}>
              <span style={{ color: '#10b981' }}>▼ faster in B</span>
              <span style={{ color: '#ef4444' }}>▲ slower in B</span>
              <span style={{ color: '#f59e0b' }}>⚡ status changed</span>
              <span style={{ color: '#6366f1' }}>← only in A</span>
              <span style={{ color: '#06b6d4' }}>→ only in B</span>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function RunChip({ run, label, color }: { run: RunSummary; label: string; color: string }) {
  const sc = STATUS_COLOR[run.status]
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '5px 12px', borderRadius: 6,
      background: color + '18', border: `1px solid ${color}44`,
    }}>
      <span style={{
        fontSize: 10, fontWeight: 800, color,
        background: color + '33', borderRadius: 3,
        padding: '1px 5px',
      }}>{label}</span>
      <span style={{ fontSize: 12, fontWeight: 600, color: '#f1f5f9', fontFamily: 'ui-monospace, monospace' }}>
        {run.name}
      </span>
      <span style={{ fontSize: 10, color: '#475569' }}>{run.id.slice(0, 6)}</span>
      <span style={{ fontSize: 10, fontWeight: 700, color: sc, textTransform: 'uppercase' }}>
        {run.status}
      </span>
    </div>
  )
}

function RunCard({ run, label, color }: { run: RunSummary; label: string; color: string }) {
  const sc = STATUS_COLOR[run.status]
  const StatusIcon = run.status === 'success' ? CheckCircle : AlertCircle

  return (
    <div style={{
      padding: 16, borderRadius: 8,
      background: '#1e293b', border: `1px solid ${color}33`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <span style={{
          fontSize: 11, fontWeight: 800, color,
          background: color + '22', borderRadius: 4, padding: '2px 8px',
        }}>Run {label}</span>
        <StatusIcon size={13} color={sc} />
        <span style={{ fontSize: 12, color: sc, fontWeight: 600, textTransform: 'uppercase' }}>
          {run.status}
        </span>
      </div>

      <div style={{ fontSize: 14, fontWeight: 700, color: '#f1f5f9', fontFamily: 'ui-monospace, monospace', marginBottom: 10 }}>
        {run.name}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        {[
          ['Duration', fmtDuration(run.duration_ms)],
          ['Spans', String(run.span_count)],
          ['Tokens', fmtTokens(run.total_tokens)],
          ['Cost', fmtCost(run.total_cost_usd)],
        ].map(([k, v]) => (
          <div key={k}>
            <div style={{ fontSize: 10, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{k}</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#e2e8f0', fontVariantNumeric: 'tabular-nums' }}>{v}</div>
          </div>
        ))}
      </div>

      {(run.tokens_exceeded || run.cost_exceeded) && (
        <div style={{
          marginTop: 10, padding: '6px 10px', borderRadius: 5,
          background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)',
          fontSize: 11, color: '#f59e0b',
        }}>
          ⚠ {run.tokens_exceeded ? 'Token budget exceeded' : 'Cost budget exceeded'}
        </div>
      )}
    </div>
  )
}

function SpanDiffRow({ diff: d }: { diff: SpanDiff }) {
  const isOnlyA = d.only_in === 'a'
  const isOnlyB = d.only_in === 'b'
  const inBoth = !d.only_in

  const delta = d.duration_delta_ms
  const deltaAbs = delta !== null ? Math.abs(delta) : null
  const faster = delta !== null && delta < 0
  // const slower = delta !== null && delta > 0
  const same = delta !== null && delta === 0

  const rowBg = isOnlyA
    ? 'rgba(99,102,241,0.06)'
    : isOnlyB
    ? 'rgba(6,182,212,0.06)'
    : d.status_changed
    ? 'rgba(245,158,11,0.06)'
    : 'transparent'

  const kc = KIND_COLOR[d.kind]

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '200px 80px 110px 110px 100px 80px 80px',
      padding: '8px 12px', gap: 8,
      background: rowBg,
      border: '1px solid #1e293b',
      borderTop: 'none',
      fontSize: 12,
      alignItems: 'center',
    }}>
      {/* Name */}
      <div style={{
        fontFamily: 'ui-monospace, monospace',
        color: isOnlyA ? '#818cf8' : isOnlyB ? '#22d3ee' : '#e2e8f0',
        fontSize: 12, fontWeight: 600,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {isOnlyA && <span style={{ color: '#6366f1', marginRight: 4 }}>←</span>}
        {isOnlyB && <span style={{ color: '#06b6d4', marginRight: 4 }}>→</span>}
        {d.name}
      </div>

      {/* Kind */}
      <div>
        <span style={{
          fontSize: 9, padding: '2px 6px', borderRadius: 3,
          background: kc.border + '22', color: kc.border,
          fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase',
        }}>{d.kind}</span>
      </div>

      {/* Duration A */}
      <div style={{ color: inBoth ? '#94a3b8' : '#334155', fontVariantNumeric: 'tabular-nums' }}>
        {isOnlyB ? <span style={{ color: '#334155' }}>—</span> : fmtDuration(d.duration_ms_a)}
      </div>

      {/* Duration B */}
      <div style={{ color: inBoth ? '#94a3b8' : '#334155', fontVariantNumeric: 'tabular-nums' }}>
        {isOnlyA ? <span style={{ color: '#334155' }}>—</span> : fmtDuration(d.duration_ms_b)}
      </div>

      {/* Delta */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        {!inBoth ? (
          <span style={{ color: '#334155', fontSize: 11 }}>N/A</span>
        ) : same ? (
          <span style={{ color: '#475569', fontSize: 11 }}>—</span>
        ) : (
          <>
            {faster
              ? <TrendingDown size={12} color="#10b981" />
              : <TrendingUp size={12} color="#ef4444" />
            }
            <span style={{
              color: faster ? '#10b981' : '#ef4444',
              fontWeight: 700, fontSize: 12,
              fontVariantNumeric: 'tabular-nums',
            }}>
              {faster ? '-' : '+'}{fmtDuration(deltaAbs)}
            </span>
          </>
        )}
      </div>

      {/* Status A */}
      <StatusBadge status={d.status_a} />

      {/* Status B */}
      <StatusBadge status={d.status_b} changed={d.status_changed} />
    </div>
  )
}

function StatusBadge({ status, changed }: { status: string | null; changed?: boolean }) {
  if (!status) return <span style={{ color: '#334155', fontSize: 11 }}>—</span>
  const sc = STATUS_COLOR[status as keyof typeof STATUS_COLOR] ?? '#64748b'
  return (
    <span style={{
      fontSize: 9, padding: '2px 6px', borderRadius: 3,
      color: sc, background: sc + '18',
      border: `1px solid ${sc}${changed ? '99' : '33'}`,
      fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
    }}>
      {changed && '⚡ '}{status}
    </span>
  )
}

function DeltaChip({
  label, delta, format,
}: {
  label: string
  delta: number | null | undefined
  format: (v: number) => string
}) {
  if (delta == null) return null
  const better = delta < 0
  const worse = delta > 0
  const color = better ? '#10b981' : worse ? '#ef4444' : '#64748b'
  const Icon = better ? TrendingDown : worse ? TrendingUp : Minus

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
      <span style={{ color: '#475569' }}>{label}:</span>
      <Icon size={12} color={color} />
      <span style={{ color, fontWeight: 700 }}>
        {delta === 0 ? '±0' : `${better ? '-' : '+'}${format(delta)}`}
      </span>
    </div>
  )
}
