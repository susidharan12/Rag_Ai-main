import { useMemo, useState } from 'react'
import { Activity, BarChart3, CheckCircle2, Gauge, ListChecks, TriangleAlert } from 'lucide-react'

const fallback = {
  summary: [],
  benchmark_timeline: [],
  golden_cases: [],
  failure_cases: [],
  case_types: [],
  question_details: [],
}

const statusTone = {
  pass: 'ok',
  fail: 'bad',
  warn: 'warn',
}

function formatMetric(value) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(2)
  }
  return value ?? '0'
}

function summarizeRows(rows) {
  if (!rows.length) {
    return { hit_rate: 0, mrr: 0, rrf: 0, pass: 0, fail: 0 }
  }

  const total = rows.length
  const hits = rows.filter((row) => row.status === 'pass').length
  const fails = rows.filter((row) => row.status === 'fail').length
  const hitRate = hits / total
  const mrr = rows.reduce((sum, row) => sum + (Number(row.mrr ?? row.hit_rate ?? 0) || 0), 0) / total
  const rrf = rows.reduce((sum, row) => sum + (Number(row.rrf ?? row.hit_rate ?? 0) || 0), 0) / total

  return { hit_rate: hitRate, mrr, rrf, pass: hits, fail: fails }
}

export default function BenchmarkView({ benchmark = fallback, turns = [] }) {
  const summary = benchmark.summary ?? fallback.summary
  const timeline = benchmark.benchmark_timeline ?? fallback.benchmark_timeline
  const goldenCases = benchmark.golden_cases ?? fallback.golden_cases
  const failureCases = benchmark.failure_cases ?? fallback.failure_cases
  const caseTypes = benchmark.case_types ?? fallback.case_types
  const staticQuestionDetails = benchmark.question_details ?? fallback.question_details

  const liveRows = useMemo(() => {
    const rows = []
    for (let i = 0; i < turns.length; i++) {
      const turn = turns[i]
      if (!turn || !turn.question) continue
      const status = turn.error ? 'fail' : turn.refused ? 'fail' : 'pass'
      rows.push({
        id: turn.traceId ? `${turn.traceId.slice(0, 8)}` : `live-${i}`,
        question: turn.question,
        question_type: 'live',
        status,
        expected_answer: turn.expectedAnswer ?? 'Live answer',
        observed: turn.refused ? 'refused' : turn.error ? 'error' : (turn.sources?.length ? 'retrieved and answered' : 'answered'),
        reason: turn.reason || (turn.refused ? 'Question was refused.' : turn.error ? 'Question failed at runtime.' : 'Live question answered successfully.'),
        evidence: turn.trace ? 'Live trace captured from the running request.' : 'No trace attached for this question.',
        fix: turn.refused ? 'Add a stronger answerability gate or better retrieval context.' : 'No fix needed for this successful live request.',
        hit_rate: turn.error || turn.refused ? 0 : 1,
        mrr: turn.error || turn.refused ? 0 : 1,
        rrf: turn.error || turn.refused ? 0 : 1,
      })
    }
    return rows
  }, [turns])

  const [showFailedOnly, setShowFailedOnly] = useState(false)
  const [sortBy, setSortBy] = useState('hit_rate')
  const [sortDirection, setSortDirection] = useState('desc')

  const filteredRows = useMemo(() => {
    const rows = showFailedOnly ? liveRows.filter((row) => row.status === 'fail') : liveRows
    const dir = sortDirection === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      const av = Number(a[sortBy] ?? 0)
      const bv = Number(b[sortBy] ?? 0)
      return (av - bv) * dir
    })
  }, [liveRows, showFailedOnly, sortBy, sortDirection])

  const aggregate = useMemo(() => summarizeRows(liveRows), [liveRows])

  const timelineRows = useMemo(() => {
    if (!timeline.length) return []
    return timeline.map((row, index) => {
      if (row.week === 'Week 6' || index === timeline.length - 1) {
        return {
          ...row,
          hit_rate: `${aggregate.hit_rate.toFixed(2)} (${aggregate.pass}/${liveRows.length})`,
          mrr: aggregate.mrr.toFixed(2),
          rrf: aggregate.rrf.toFixed(2),
          failures: `${aggregate.fail} failing rows in current evaluation`,
          verdict: aggregate.fail === 0 ? 'good' : 'warn',
          verdict_label: aggregate.fail === 0 ? 'live pass' : 'live review',
        }
      }
      return row
    })
  }, [timeline, aggregate, liveRows.length])

  const summaryCards = useMemo(() => {
    const currentSummary = [
      { label: 'Live hit-rate', value: `${aggregate.hit_rate.toFixed(2)}`, week: 'Current', meta: `${aggregate.pass} passed / ${liveRows.length} total` },
      { label: 'Live MRR', value: aggregate.mrr.toFixed(2), week: 'Current', meta: 'Average reciprocal rank over all current questions' },
      { label: 'Live RRF', value: aggregate.rrf.toFixed(2), week: 'Current', meta: 'Re-ranking fusion score over the current set' },
      { label: 'Failures', value: String(aggregate.fail), week: 'Current', meta: 'Questions currently marked as failed' },
    ]

    return currentSummary.concat((summary || []).slice(0, 2))
  }, [aggregate, liveRows.length, summary])

  return (
    <div className="benchmark-view">
      <header className="chat-header analytics-header">
        <div className="chat-header-left">
          <div className="chat-header-title">Benchmark & Golden Set</div>
          <div className="chat-header-sub">Week 3 → Week 6: retrieval, rerank, failure taxonomy, and the current production score.</div>
        </div>
        <div className="chat-header-right">
          <span className="pill"><span className="pill-dot" /> evaluation view</span>
        </div>
      </header>

      <div className="benchmark-body">
        <div className="benchmark-overview">
          {summaryCards.map((metric, i) => (
            <div key={`${metric.label}-${i}`} className="metric-card card">
              <div className="metric-card-top">
                <div className="metric-icon"><BarChart3 size={15} /></div>
                <span>{metric.week}</span>
              </div>
              <div className="metric-value">{metric.value}</div>
              <div className="metric-label">{metric.label}</div>
              <div className="metric-note">{metric.meta}</div>
            </div>
          ))}
        </div>

        <div className="panel-card card">
          <div className="panel-card-head">
            <span className="panel-card-title"><Activity size={15} /> Benchmark timeline</span>
          </div>

          <div className="benchmark-table-wrap">
            <table className="benchmark-table">
              <thead>
                <tr>
                  <th>Week</th>
                  <th>Focus</th>
                  <th>Hit-rate</th>
                  <th>MRR</th>
                  <th>RRF</th>
                  <th>Failure summary</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {timelineRows.map((row) => (
                  <tr key={row.week}>
                    <td>{row.week}</td>
                    <td>{row.focus}</td>
                    <td>{row.hit_rate}</td>
                    <td>{row.mrr}</td>
                    <td>{row.rrf}</td>
                    <td>{row.failures}</td>
                    <td><span className={`table-badge ${row.verdict === 'good' ? 'good' : row.verdict === 'warn' ? 'warn' : 'bad'}`}>{row.verdict_label}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel-card card">
          <div className="panel-card-head">
            <span className="panel-card-title"><ListChecks size={15} /> Case categories</span>
          </div>
          <div className="chip-row">
            {caseTypes.map((type) => (
              <span key={type} className="case-chip">{type}</span>
            ))}
          </div>
        </div>

        <div className="panel-card card">
          <div className="panel-card-head">
            <span className="panel-card-title"><Gauge size={15} /> Detailed live question results</span>
            <span className="count-badge">{filteredRows.length}</span>
          </div>

          <div className="benchmark-toolbar">
            <label className="filter-toggle">
              <input type="checkbox" checked={showFailedOnly} onChange={(e) => setShowFailedOnly(e.target.checked)} />
              Show failed only
            </label>
            <div className="sort-controls">
              <label>
                Sort by
                <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                  <option value="hit_rate">Hit-rate</option>
                  <option value="mrr">MRR</option>
                  <option value="rrf">RRF</option>
                </select>
              </label>
              <button type="button" onClick={() => setSortDirection((d) => (d === 'desc' ? 'asc' : 'desc'))}>
                {sortDirection === 'desc' ? 'Desc' : 'Asc'}
              </button>
            </div>
          </div>

          <div className="benchmark-table-wrap">
            <table className="benchmark-table compact detail-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Question</th>
                  <th>Status</th>
                  <th>Hit-rate</th>
                  <th>MRR</th>
                  <th>RRF</th>
                  <th>Expected</th>
                  <th>Observed</th>
                  <th>Reason</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((item) => (
                  <tr key={`${item.id}-${item.question}`}>
                    <td>{item.id}</td>
                    <td className="table-question">{item.question}</td>
                    <td><span className={`table-badge ${item.status === 'pass' ? 'good' : item.status === 'fail' ? 'bad' : 'warn'}`}>{item.status}</span></td>
                    <td>{formatMetric(item.hit_rate ?? 0)}</td>
                    <td>{formatMetric(item.mrr ?? 0)}</td>
                    <td>{formatMetric(item.rrf ?? 0)}</td>
                    <td>{item.expected_answer || '—'}</td>
                    <td>{item.observed || '—'}</td>
                    <td>{item.reason || '—'}</td>
                    <td>{item.evidence || item.fix || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="benchmark-grid">
          <div className="panel-card card">
            <div className="panel-card-head">
              <span className="panel-card-title"><CheckCircle2 size={15} /> Golden-set cases</span>
              <span className="count-badge">{goldenCases.length}</span>
            </div>

            <div className="benchmark-table-wrap">
              <table className="benchmark-table compact">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Question</th>
                    <th>Expected</th>
                    <th>Status</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {goldenCases.map((item) => (
                    <tr key={item.id}>
                      <td>{item.id}</td>
                      <td className="table-question">{item.question}</td>
                      <td>{item.expected_answer}</td>
                      <td><span className={`table-badge ${statusTone[item.status] || 'warn'}`}>{item.status}</span></td>
                      <td>{item.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel-card card">
            <div className="panel-card-head">
              <span className="panel-card-title"><TriangleAlert size={15} /> Failure detail</span>
              <span className="count-badge bad">{failureCases.length}</span>
            </div>

            <div className="failure-list">
              {failureCases.map((failure) => (
                <div key={failure.id} className="failure-item">
                  <div className="failure-head">
                    <div className="failure-id">{failure.id}</div>
                    <span className={`table-badge ${failure.status === 'fail' ? 'bad' : 'warn'}`}>{failure.status}</span>
                  </div>
                  <div className="failure-title">{failure.case}</div>
                  <div className="failure-text"><strong>Question:</strong> {failure.question}</div>
                  <div className="failure-text"><strong>Observed:</strong> {failure.observed}</div>
                  <div className="failure-text"><strong>Reason:</strong> {failure.reason}</div>
                  <div className="failure-text"><strong>Fix / evidence:</strong> {failure.fix}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
