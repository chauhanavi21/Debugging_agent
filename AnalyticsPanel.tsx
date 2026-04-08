import { useState, useEffect } from 'react'
import { TrendingUp, Cpu, DollarSign, Zap, AlertTriangle } from 'lucide-react'
import type { SlowSpan, ModelUsage } from '../types'
import { api } from '../lib/api'
import { KIND_COLOR, fmtDuration, fmtCost, fmtTokens } from '../lib/styles'

interface Props {
  // In demo mode we pass mock data directly
  mockSlowSpans?: SlowSpan[]
  mockModelUsage?: ModelUsage[]
}

export function AnalyticsPanel({ mockSlowSpans, mockModelUsage }: Props) {
  const [slowSpans, setSlowSpans] = useState<SlowSpan[]>(mockSlowSpans ?? [])
  const [modelUsage, setModelUsage] = useState<ModelUsage[]>(mockModelUsage ?? [])
  const [kindFilter, setKindFilter] = useState<string>('')
  const [loading, setLoading] = useState(!mockSlowSpans)

  useEffect(() => {
    if (mockSlowSpans) { setSlowSpans(mockSlowSpans); setModelUsage(mockModelUsage ?? []); return }
    setLoading(true)
    Promise.all([
      api.analytics.slowSpans(kindFilter || undefined),
      api.analytics.modelUsage(),
    ]).then(([s, m]) => { setSlowSpans(s); setModelUsage(m) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [kindFilter, mockSlowSpans, mockModelUsage])

  const maxAvgMs = Math.max(...slowSpans.map(s => s.avg_ms), 1)
  const maxCost = Math.max(...modelUsage.map(m => m.total_cost_usd), 0.0001)
  const totalCost = modelUsage.reduce((a, m) => a + m.total_cost_usd, 0)
  const totalCalls = modelUsage.reduce((a, m) => a + m.call_count, 0)

  const KINDS = ['agent', 'tool', 'llm', 'retrieval', 'chain']

  return (
    <div style={{
      flex: 1, overflowY: 'auto',
      padding: '24px 28px',
      background: '#020617',
      fontFamily: 'ui-sans-serif, sans-serif',
    }}>
      {loading && (
        <div style={{ color: '#475569', fontSize: 13, padding: 40, textAlign: 'center' }}>
          Loading analytics…
        </div>
      )}

      {!loading && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, maxWidth: 1100 }}>

          {/* ── Slow Spans ───────────────────────────────── */}
          <div style={{ gridColumn: '1 / -1' }}>
            <SectionHeader
              icon={<TrendingUp size={14} />}
              title="Slowest Spans"
              subtitle="Average duration across all runs — find your bottlenecks"
            >
              {/* Kind filter */}
              <div style={{ display: 'flex', gap: 6 }}>
                {['', ...KINDS].map(k => (
                  <button key={k} onClick={() => setKindFilter(k)} style={{
                    padding: '3px 10px', borderRadius: 5, cursor: 'pointer',
                    fontSize: 10, fontWeight: 600, textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    background: kindFilter === k ? '#6366f1' : 'transparent',
                    border: `1px solid ${kindFilter === k ? '#6366f1' : '#1e293b'}`,
                    color: kindFilter === k ? '#fff' : '#475569',
                  }}>{k || 'all'}</button>
                ))}
              </div>
            </SectionHeader>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {slowSpans.length === 0 && (
                <Empty msg="No span data yet — run some agents first." />
              )}
              {slowSpans.map((span, i) => {
                const kc = KIND_COLOR[span.kind] ?? KIND_COLOR.custom
                const barW = (span.avg_ms / maxAvgMs) * 100
                const errRate = span.call_count > 0 ? (span.error_count / span.call_count) * 100 : 0

                return (
                  <div key={i} style={{
                    padding: '10px 14px', borderRadius: 8,
                    background: '#0f172a', border: '1px solid #1e293b',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                      {/* Rank */}
                      <span style={{ fontSize: 11, color: '#334155', fontWeight: 700, minWidth: 18, textAlign: 'right' }}>
                        #{i + 1}
                      </span>

                      {/* Kind badge */}
                      <span style={{
                        fontSize: 9, padding: '2px 6px', borderRadius: 3,
                        background: kc.border + '22', color: kc.border,
                        fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
                      }}>{span.kind}</span>

                      {/* Name */}
                      <span style={{
                        fontSize: 13, fontWeight: 600, color: '#e2e8f0',
                        fontFamily: 'ui-monospace, monospace', flex: 1,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>{span.name}</span>

                      {/* Error rate warning */}
                      {errRate > 5 && (
                        <span style={{
                          display: 'flex', alignItems: 'center', gap: 3,
                          fontSize: 10, color: '#ef4444', fontWeight: 700,
                        }}>
                          <AlertTriangle size={10} /> {errRate.toFixed(0)}% err
                        </span>
                      )}

                      {/* Stats */}
                      <div style={{ display: 'flex', gap: 14, fontSize: 12 }}>
                        <Stat label="avg" value={fmtDuration(span.avg_ms)} highlight />
                        <Stat label="max" value={fmtDuration(span.max_ms)} />
                        <Stat label="calls" value={span.call_count.toLocaleString()} />
                      </div>
                    </div>

                    {/* Bar */}
                    <div style={{ height: 4, background: '#1e293b', borderRadius: 2, overflow: 'hidden' }}>
                      <div style={{
                        height: '100%', borderRadius: 2,
                        width: `${barW}%`,
                        background: errRate > 20
                          ? '#ef4444'
                          : barW > 80
                          ? '#f59e0b'
                          : kc.border,
                        transition: 'width 0.4s ease',
                      }} />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* ── Model Usage ──────────────────────────────── */}
          <div>
            <SectionHeader
              icon={<Cpu size={14} />}
              title="Model Usage"
              subtitle={`${totalCalls.toLocaleString()} calls · ${fmtCost(totalCost)} total`}
            />

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {modelUsage.length === 0 && (
                <Empty msg="No LLM calls traced yet." />
              )}
              {modelUsage.map((m, i) => {
                const barW = (m.total_cost_usd / maxCost) * 100
                const pct = totalCost > 0 ? ((m.total_cost_usd / totalCost) * 100).toFixed(0) : '0'

                return (
                  <div key={i} style={{
                    padding: '12px 14px', borderRadius: 8,
                    background: '#0f172a', border: '1px solid #1e293b',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
                      <div>
                        <div style={{
                          fontSize: 13, fontWeight: 700, color: '#f1f5f9',
                          fontFamily: 'ui-monospace, monospace', marginBottom: 2,
                        }}>{m.model}</div>
                        {m.provider && (
                          <div style={{ fontSize: 10, color: '#475569' }}>via {m.provider}</div>
                        )}
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: 14, fontWeight: 800, color: '#f59e0b' }}>
                          {fmtCost(m.total_cost_usd)}
                        </div>
                        <div style={{ fontSize: 10, color: '#475569' }}>{pct}% of total</div>
                      </div>
                    </div>

                    {/* Cost bar */}
                    <div style={{ height: 3, background: '#1e293b', borderRadius: 2, marginBottom: 10, overflow: 'hidden' }}>
                      <div style={{
                        height: '100%', borderRadius: 2,
                        width: `${barW}%`, background: '#f59e0b',
                        transition: 'width 0.4s ease',
                      }} />
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                      <MiniStat icon={<Zap size={10} />} label="Calls" value={m.call_count.toLocaleString()} />
                      <MiniStat icon={<DollarSign size={10} />} label="Input tok" value={fmtTokens(m.input_tokens)} />
                      <MiniStat icon={<DollarSign size={10} />} label="Output tok" value={fmtTokens(m.output_tokens)} />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* ── Cost over time placeholder ────────────────── */}
          <div>
            <SectionHeader
              icon={<DollarSign size={14} />}
              title="Cost Breakdown"
              subtitle="Spend by model"
            />

            {modelUsage.length === 0 ? (
              <Empty msg="No cost data yet." />
            ) : (
              <div style={{ padding: 16, borderRadius: 8, background: '#0f172a', border: '1px solid #1e293b' }}>
                {/* Simple donut-style legend */}
                {modelUsage.slice(0, 6).map((m, i) => {
                  const PALETTE = ['#6366f1','#06b6d4','#f59e0b','#10b981','#8b5cf6','#ef4444']
                  const color = PALETTE[i % PALETTE.length]
                  const pct = totalCost > 0 ? ((m.total_cost_usd / totalCost) * 100) : 0

                  return (
                    <div key={i} style={{ marginBottom: 10 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
                          <span style={{ fontSize: 12, color: '#94a3b8', fontFamily: 'ui-monospace, monospace' }}>
                            {m.model.length > 22 ? m.model.slice(0, 22) + '…' : m.model}
                          </span>
                        </div>
                        <span style={{ fontSize: 12, color: '#64748b' }}>{pct.toFixed(1)}%</span>
                      </div>
                      <div style={{ height: 4, background: '#1e293b', borderRadius: 2, overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 2, transition: 'width 0.5s ease' }} />
                      </div>
                    </div>
                  )
                })}

                <div style={{
                  marginTop: 14, paddingTop: 12, borderTop: '1px solid #1e293b',
                  display: 'flex', justifyContent: 'space-between',
                  fontSize: 12,
                }}>
                  <span style={{ color: '#475569' }}>Total across all models</span>
                  <span style={{ color: '#f59e0b', fontWeight: 800 }}>{fmtCost(totalCost)}</span>
                </div>
              </div>
            )}
          </div>

        </div>
      )}
    </div>
  )
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function SectionHeader({ icon, title, subtitle, children }: {
  icon: React.ReactNode; title: string; subtitle: string; children?: React.ReactNode
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
          <span style={{ color: '#6366f1' }}>{icon}</span>
          <span style={{ fontSize: 13, fontWeight: 700, color: '#f1f5f9' }}>{title}</span>
        </div>
        <div style={{ fontSize: 11, color: '#475569' }}>{subtitle}</div>
      </div>
      {children}
    </div>
  )
}

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={{ textAlign: 'right' }}>
      <span style={{ fontSize: 11, color: '#475569', marginRight: 3 }}>{label}</span>
      <span style={{ fontSize: 12, fontWeight: highlight ? 700 : 400, color: highlight ? '#e2e8f0' : '#64748b', fontVariantNumeric: 'tabular-nums' }}>{value}</span>
    </div>
  )
}

function MiniStat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <span style={{ color: '#334155' }}>{icon}</span>
      <div>
        <div style={{ fontSize: 9, color: '#334155', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
        <div style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600 }}>{value}</div>
      </div>
    </div>
  )
}

function Empty({ msg }: { msg: string }) {
  return (
    <div style={{ padding: '28px 16px', textAlign: 'center', color: '#334155', fontSize: 12, borderRadius: 8, border: '1px dashed #1e293b' }}>
      {msg}
    </div>
  )
}
