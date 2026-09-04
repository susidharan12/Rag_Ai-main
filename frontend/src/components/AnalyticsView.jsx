import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  Activity,
  CheckCircle2,
  ChevronDown,
  FileSearch,
  Layers,
  ListChecks,
  TriangleAlert,
  XCircle,
} from 'lucide-react'
import JudgeValidationPanel from './JudgeValidationPanel.jsx'

function pct(n) {
  if (!n) return '0%'
  return `${Math.round(n)}%`
}

export default function AnalyticsView({ stats, turns, judgeEval }) {
  const [expanded, setExpanded] = useState(null)

  const total = turns.length
  const failures = turns.filter((t) => t.refused || t.error)
  const ok = turns.filter((t) => !t.refused && !t.error)
  const successRate = total ? (ok.length / total) * 100 : 0
  const avgSources = ok.length
    ? ok.reduce((a, t) => a + t.sources.length, 0) / ok.length
    : 0
  const avgLatency = ok.length
    ? ok.reduce((a, t) => a + (t.latencyMs?.total ?? t.latencyMs ?? 0), 0) / ok.length
    : 0

  const sections = [
    { label: 'Successful', value: ok.length, Icon: CheckCircle2, tone: 'good' },
    { label: 'Refused', value: failures.length, Icon: XCircle, tone: 'bad' },
    { label: 'Avg sources / answer', value: avgSources.toFixed(1), Icon: FileSearch, tone: 'indigo' },
    { label: 'Avg latency', value: avgLatency ? `${Math.round(avgLatency)}ms` : '–', Icon: Activity, tone: 'teal' },
  ]

  const toggle = (i) => setExpanded(expanded === i ? null : i)

  return (
    <div className="analytics">
      <header className="chat-header analytics-header">
        <div className="chat-header-left">
          <div className="chat-header-title">Analytics</div>
          <div className="chat-header-sub">Hit rates · traces · failures</div>
        </div>
        <div className="chat-header-right">
          <span className="pill"><span className="pill-dot" /> live session</span>
        </div>
      </header>

      <div className="analytics-body">
        <JudgeValidationPanel data={judgeEval} />

        {!total ? (
          <div className="hero-empty">
            <div className="hero-orb"><Activity size={24} /></div>
            <h2>No session data yet</h2>
            <p>Ask a question in the chat and this panel will live-track hit rate, traces and any failures.</p>
          </div>
        ) : (
          <>
            <div className="analytics-overview">
              <div className="analytics-head">
                <div>
                  <div className="analytics-label">Session success rate</div>
                  <div className="analytics-title">{pct(successRate)}</div>
                </div>
                <div className="success-ring">
                  <svg width="72" height="72" viewBox="0 0 72 72">
                    <defs>
                      <linearGradient id="grades" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor="#4f46e5" />
                        <stop offset="100%" stopColor="#0d9488" />
                      </linearGradient>
                    </defs>
                    <circle cx="36" cy="36" r="30" fill="none" stroke="rgba(0,0,0,0.08)" strokeWidth="7" />
                    <circle
                      cx="36" cy="36" r="30" fill="none"
                      stroke="url(#grades)" strokeWidth="7" strokeLinecap="round"
                      strokeDasharray={2 * Math.PI * 30}
                      strokeDashoffset={2 * Math.PI * 30 * (1 - successRate / 100)}
                    />
                  </svg>
                  <span>{total}</span>
                </div>
              </div>

              <div className="analytics-grid">
                {sections.map(({ label, value, Icon, tone }, i) => (
                  <motion.div
                    key={label}
                    className="tile card"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.05 }}
                  >
                    <div className={`tile-icon ${tone}`}><Icon size={16} /></div>
                    <div className="tile-label">{label}</div>
                    <div className="tile-value">{value}</div>
                  </motion.div>
                ))}
              </div>
            </div>

            <div className="analytics-panels">
              <div className="panel-card card">
                <div className="panel-card-head">
                  <span className="panel-card-title"><ListChecks size={15} /> Traces</span>
                  <span className="count-badge">{turns.length}</span>
                </div>
                <div className="trace-list">
                  {turns.map((t, i) => (
                    <div key={i} className="trace-block">
                      <button className={`trace-row ${t.refused || t.error ? 'fail' : ''} ${expanded === i ? 'open' : ''}`} onClick={() => toggle(i)}>
                        <div className="trace-q">
                          {t.question}
                          {t.trace && <span className="trace-toggle"><ChevronDown size={14} /></span>}
                        </div>
                        <div className="trace-meta">
                          <span className="trace-id mono">{t.traceId ? t.traceId.slice(0, 14) + '…' : 'no trace'}</span>
                          {t.latencyMs?.total != null && <span className="mono">{Math.round(t.latencyMs.total)}ms</span>}
                          <span className={`badge ${t.error ? 'err' : t.refused ? 'ref' : 'ok'}`}>
                            {t.error ? 'error' : t.refused ? 'refused' : 'ok'}
                          </span>
                        </div>
                      </button>
                      {expanded === i && t.trace && <TraceReport trace={t.trace} />}
                    </div>
                  ))}
                </div>
              </div>

              <div className="panel-card card">
                <div className="panel-card-head">
                  <span className="panel-card-title"><TriangleAlert size={15} /> Failures</span>
                  <span className="count-badge bad">{failures.length}</span>
                </div>
                {failures.length ? (
                  <div className="trace-list">
                    {failures.map((t, i) => (
                      <div key={i} className="fail-block">
                        <div className="fail-row">
                          <div className="trace-q">{t.question}</div>
                          <div className="trace-meta">
                            <span className={`badge ${t.error ? 'err' : 'ref'}`}>
                              {t.error ? 'error' : 'refused'}
                            </span>
                          </div>
                        </div>
                        {t.reason && (
                          <div className={`fail-reason ${t.error ? 'err' : 'ref'}`}>{t.reason}</div>
                        )}
                        {t.error && t.traceId && t.trace && (
                          <details className="fail-trace">
                            <summary>View failed trace report</summary>
                            <TraceReport trace={t.trace} />
                          </details>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">
                    <CheckCircle2 size={16} />
                    No failures recorded
                  </div>
                )}
              </div>

              <div className="panel-card card">
                <div className="panel-card-head">
                  <span className="panel-card-title"><Layers size={15} /> Corpus</span>
                </div>
                <div className="corpus-grid">
                  <div className="corpus-cell"><span>Documents</span><b>{stats?.documents ?? 0}</b></div>
                  <div className="corpus-cell"><span>Chunks</span><b>{stats?.chunks ?? 0}</b></div>
                  <div className="corpus-cell"><span>Questions</span><b>{total}</b></div>
                  <div className="corpus-cell"><span>Versions</span><b>{Object.keys(stats?.by_sdk_version || {}).length}</b></div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function TraceReport({ trace }) {
  return (
    <div className="trace-report">
      <div className="trace-report-row">
        <span>trace_id</span><code className="mono">{trace.trace_id}</code>
      </div>
      <div className="trace-report-row"><span>ts_utc</span><code>{trace.ts_utc}</code></div>
      <div className="trace-report-row"><span>surface</span><code>{trace.surface}</code></div>
      <div className="trace-report-row"><span>model</span><code>{trace.generation?.model}</code></div>
      <div className="trace-report-row"><span>prompt_version</span><code>{trace.generation?.prompt_version}</code></div>
      {trace.generation?.params && (
        <div className="trace-report-group">
          <div className="trace-report-group-title">generation.params</div>
          <pre className="trace-report-pre">{JSON.stringify(trace.generation.params, null, 2)}</pre>
        </div>
      )}
      <div className="trace-report-group">
        <div className="trace-report-group-title">latency_ms</div>
        <pre className="trace-report-pre">{JSON.stringify(trace.latency_ms, null, 2)}</pre>
      </div>
      <div className="trace-report-group">
        <div className="trace-report-group-title">retrieval</div>
        <pre className="trace-report-pre">{JSON.stringify(trace.retrieval, null, 2)}</pre>
      </div>
      <div className="trace-report-group">
        <div className="trace-report-group-title">raw_output</div>
        <pre className="trace-report-pre">{trace.raw_output}</pre>
      </div>
    </div>
  )
}
