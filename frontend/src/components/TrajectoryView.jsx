import { useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  GitBranch,
  Target,
  Gauge,
  TrendingDown,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ShieldAlert,
  ChevronDown,
  ChevronRight,
  ListChecks,
  Wrench,
} from 'lucide-react'

const TOOL_COLORS = {
  search_docs: '#4f46e5',
  get_version_info: '#7c3aed',
  compare_versions: '#0d9488',
  get_error_info: '#ef4444',
  get_parameter_default: '#d97706',
  check_deprecation: '#db2777',
  finish: '#10b981',
}

function pct(v) {
  if (v === null || v === undefined) return '—'
  return `${(v * 100).toFixed(0)}%`
}

function fmtMs(v) {
  if (v === null || v === undefined) return '—'
  return `${(v / 1000).toFixed(1)}s`
}

function fmtUsd(v) {
  if (v === null || v === undefined) return '—'
  return `$${v.toFixed(6)}`
}

function deltaBadge(delta) {
  if (delta === 0) return <span className="table-badge warn">no change</span>
  if (delta < 0) return <span className="table-badge good">{delta}</span>
  return <span className="table-badge bad">+{delta}</span>
}

function TagChips({ tags }) {
  if (!tags || !tags.length) return <span className="table-badge ok">clean</span>
  return (
    <div className="chip-row">
      {tags.map((t) => (
        <span key={t} className="case-chip traj-tag">{t}</span>
      ))}
    </div>
  )
}

function TraceStep({ step, index }) {
  const [expanded, setExpanded] = useState(index < 2)
  const color = TOOL_COLORS[step.tool] || '#71717a'
  return (
    <div className="agent-step">
      <div className="agent-step-header" onClick={() => setExpanded(!expanded)}>
        <div className="agent-step-number" style={{ background: color }}>{step.step}</div>
        <div className="agent-step-meta">
          <div className="agent-step-tool" style={{ color }}>
            {step.tool === 'finish' ? <CheckCircle2 size={13} /> : <ChevronRight size={13} />}
            {step.tool}
          </div>
          <div className="agent-step-thought">
            {step.thought?.length > 90 ? step.thought.slice(0, 90) + '...' : step.thought}
          </div>
        </div>
        <button className="agent-step-toggle">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
      </div>
      <AnimatePresence>
        {expanded && (
          <motion.div
            className="agent-step-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {step.args && Object.keys(step.args).length > 0 && (
              <div className="agent-step-section">
                <div className="agent-step-label">Tool Arguments</div>
                <pre className="agent-step-args">{JSON.stringify(step.args, null, 2)}</pre>
              </div>
            )}
            <div className="agent-step-section">
              <div className="agent-step-label">Observation</div>
              <div className="agent-step-observation">{step.observation}</div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function ConditionCard({ label, tone, data, metrics }) {
  return (
    <div className={`race-card ${tone}-card`}>
      <div className="race-card-header">
        {tone === 'before' ? <XCircle size={18} /> : <CheckCircle2 size={18} />}
        <span>{label}</span>
      </div>
      <div className="race-card-stats">
        <div className="race-stat">
          <span className="race-stat-label">Outcome pass rate</span>
          <span className="race-stat-value">{pct(data.outcome_pass_rate)}</span>
        </div>
        <div className="race-stat">
          <span className="race-stat-label">Trajectory pass rate</span>
          <span className="race-stat-value">{pct(data.trajectory_pass_rate)}</span>
        </div>
        <div className="race-stat">
          <span className="race-stat-label">Gap</span>
          <span className="race-stat-value">{data.gap >= 0 ? '+' : ''}{data.gap.toFixed(2)}</span>
        </div>
        <div className="race-stat">
          <span className="race-stat-label">Tool-choice accuracy</span>
          <span className="race-stat-value">{pct(metrics.tool_choice_accuracy)}</span>
        </div>
        <div className="race-stat">
          <span className="race-stat-label">Argument validity</span>
          <span className="race-stat-value">{pct(metrics.argument_validity_rate)}</span>
        </div>
        <div className="race-stat">
          <span className="race-stat-label">Step efficiency (mean)</span>
          <span className="race-stat-value">{metrics.step_efficiency.mean}x</span>
        </div>
        <div className="race-stat">
          <span className="race-stat-label">Cost p50 / max</span>
          <span className="race-stat-value">
            {fmtUsd(metrics.cost_distribution_usd.p50)} / {fmtUsd(metrics.cost_distribution_usd.max)}
          </span>
        </div>
        <div className="race-stat">
          <span className="race-stat-label">Latency p50 / max</span>
          <span className="race-stat-value">
            {fmtMs(metrics.latency_distribution_ms.p50)} / {fmtMs(metrics.latency_distribution_ms.max)}
          </span>
        </div>
      </div>
    </div>
  )
}

const fallback = { available: false, reason: 'Not loaded yet.' }

export default function TrajectoryView({ trajectoryEval = fallback }) {
  const [bonusOpen, setBonusOpen] = useState(false)
  const [traceOpen, setTraceOpen] = useState(true)

  const available = trajectoryEval?.available
  const report = trajectoryEval?.report
  const perQuery = trajectoryEval?.per_query || []
  const bonus = trajectoryEval?.bonus

  const touchedQueries = useMemo(
    () => perQuery.filter((q) => (q.after?.deprecation_holds || 0) > 0),
    [perQuery],
  )

  if (!available) {
    return (
      <div className="agent-view">
        <div className="race-empty">
          <GitBranch size={40} strokeWidth={1.5} />
          <h3>Trajectory Evals</h3>
          <p>
            {trajectoryEval?.reason ||
              "week8_trajectory_eval/report.json not found. Run `python -m week8_trajectory_eval.trajectory_eval` " +
              'to generate real before/after agent traces, then reload this tab.'}
          </p>
        </div>
      </div>
    )
  }

  const fp = report.false_positive_trace
  const mit = report.mitigation

  return (
    <div className="benchmark-view">
      <header className="chat-header analytics-header">
        <div className="chat-header-left">
          <div className="chat-header-icon tone-3"><GitBranch size={18} /></div>
          <div>
            <div className="chat-header-title">Trajectory Evals</div>
            <div className="chat-header-sub">
              Week 8: did the agent get the right answer via a verified tool path, or just get lucky? Real runs, real gap.
            </div>
          </div>
        </div>
        <div className="chat-header-right">
          <span className="pill pill-good"><span className="pill-dot" /> {report.n_queries} real queries</span>
        </div>
      </header>

      <div className="benchmark-body">
        {/* Top overview cards */}
        <div className="benchmark-overview">
          <div className="metric-card card tone-0">
            <div className="metric-card-top"><div className="metric-icon"><Target size={15} /></div><span>Before</span></div>
            <div className="metric-value">+{report.before.gap.toFixed(2)}</div>
            <div className="metric-label">Outcome − Trajectory gap</div>
            <div className="metric-note">{pct(report.before.outcome_pass_rate)} outcome vs {pct(report.before.trajectory_pass_rate)} trajectory</div>
          </div>
          <div className="metric-card card tone-1">
            <div className="metric-card-top"><div className="metric-icon"><Target size={15} /></div><span>After</span></div>
            <div className="metric-value">+{report.after.gap.toFixed(2)}</div>
            <div className="metric-label">Outcome − Trajectory gap</div>
            <div className="metric-note">{pct(report.after.outcome_pass_rate)} outcome vs {pct(report.after.trajectory_pass_rate)} trajectory</div>
          </div>
          <div className="metric-card card tone-2">
            <div className="metric-card-top"><div className="metric-icon"><Wrench size={15} /></div><span>Mitigation target</span></div>
            <div className="metric-value">{mit.before_count}→{mit.after_count}</div>
            <div className="metric-label">{mit.target_failure_mode}</div>
            <div className="metric-note">{deltaBadge(mit.delta)}</div>
          </div>
          <div className="metric-card card tone-3">
            <div className="metric-card-top"><div className="metric-icon"><Gauge size={15} /></div><span>Step efficiency</span></div>
            <div className="metric-value">{report.before.metrics.step_efficiency.mean}x → {report.after.metrics.step_efficiency.mean}x</div>
            <div className="metric-label">Mean actual / optimal steps</div>
            <div className="metric-note">1.0x = always optimal</div>
          </div>
        </div>

        {/* Before / After comparison */}
        <div className="panel-card card">
          <div className="panel-card-head">
            <span className="panel-card-title"><GitBranch size={15} /> Before vs. After the mitigation</span>
          </div>
          <div className="race-comparison">
            <ConditionCard label="Before (shipped default)" tone="before" data={report.before} metrics={report.before.metrics} />
            <div className="race-vs">VS</div>
            <ConditionCard label="After (enforce_deprecation_check)" tone="after" data={report.after} metrics={report.after.metrics} />
          </div>
        </div>

        {/* False positive trace */}
        <div className="panel-card card">
          <div className="panel-card-head" onClick={() => setTraceOpen(!traceOpen)} style={{ cursor: 'pointer' }}>
            <span className="panel-card-title"><AlertTriangle size={15} /> False-positive trace: right answer, wrong path ({fp.id})</span>
            {traceOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
          </div>
          {traceOpen && (
            <div>
              <p className="race-subtitle">{fp.question}</p>
              <div className="chip-row" style={{ marginBottom: 12 }}>
                <span className="table-badge good">outcome PASS (score {fp.outcome_score.toFixed(2)})</span>
                <span className="table-badge bad">trajectory FAIL</span>
                {fp.failure_tags.map((t) => <span key={t} className="case-chip traj-tag">{t}</span>)}
                <span className="table-badge warn">stopped_by: {fp.stopped_by}</span>
              </div>
              <div className="agent-steps-container">
                {fp.steps.map((s, i) => <TraceStep key={i} step={s} index={i} />)}
              </div>
            </div>
          )}
        </div>

        {/* Mitigation detail + isolated price */}
        <div className="panel-card card">
          <div className="panel-card-head">
            <span className="panel-card-title"><Wrench size={15} /> The one mitigation, and its isolated price</span>
          </div>
          <p className="race-subtitle">{mit.fix}</p>
          <div className="benchmark-table-wrap">
            <table className="benchmark-table compact">
              <thead>
                <tr><th>Query</th><th>Gate fired?</th><th>Trajectory</th><th>Latency Δ</th><th>Tokens Δ</th><th>Cost Δ</th></tr>
              </thead>
              <tbody>
                {touchedQueries.map((q) => (
                  <tr key={q.id}>
                    <td>{q.id}</td>
                    <td><span className="table-badge good">1 hold</span></td>
                    <td><span className={`table-badge ${q.after.trajectory_pass ? 'good' : 'warn'}`}>{q.after.trajectory_pass ? 'PASS' : 'still FAIL (partial)'}</span></td>
                    <td>{q.after.latency_ms && q.before.latency_ms ? `+${((q.after.latency_ms - q.before.latency_ms) / 1000).toFixed(1)}s` : '—'}</td>
                    <td>{q.after.est_tokens && q.before.est_tokens ? (q.after.est_tokens - q.before.est_tokens) : '—'}</td>
                    <td>{q.after.est_cost_usd !== undefined && q.before.est_cost_usd !== undefined ? `$${(q.after.est_cost_usd - q.before.est_cost_usd).toFixed(6)}` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="race-subtitle" style={{ marginTop: 10 }}>
            <TrendingDown size={13} style={{ verticalAlign: 'text-bottom' }} /> The aggregate before/after numbers (top cards) are confounded
            by ordinary run-to-run LLM variance on the {perQuery.length - touchedQueries.length} queries the gate never touched
            (verified via the <code>deprecation_holds</code> metric) — the table above is the honest, isolated price.
          </p>
        </div>

        {/* Regression matrix */}
        <div className="panel-card card">
          <div className="panel-card-head">
            <span className="panel-card-title"><ListChecks size={15} /> Regression matrix</span>
            <span className="count-badge">{report.regression_matrix.length} modes</span>
          </div>
          <div className="benchmark-table-wrap">
            <table className="benchmark-table compact">
              <thead>
                <tr><th>Failure mode</th><th>Before</th><th>After</th><th>Δ</th><th>Regressed?</th></tr>
              </thead>
              <tbody>
                {report.regression_matrix.map((row) => (
                  <tr key={row.failure_mode}>
                    <td>{row.failure_mode}</td>
                    <td>{row.before}</td>
                    <td>{row.after}</td>
                    <td>{deltaBadge(row.delta)}</td>
                    <td>{row.regressed ? <span className="table-badge bad">yes</span> : <span className="table-badge ok">no</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Per-query detail */}
        <div className="panel-card card">
          <div className="panel-card-head">
            <span className="panel-card-title"><Gauge size={15} /> All 10 queries — before vs. after</span>
            <span className="count-badge">{perQuery.length}</span>
          </div>
          <div className="benchmark-table-wrap">
            <table className="benchmark-table compact detail-table">
              <thead>
                <tr>
                  <th>ID</th><th>Question</th>
                  <th>Before outcome</th><th>Before traj.</th><th>Before tags</th>
                  <th>After outcome</th><th>After traj.</th><th>After tags</th>
                </tr>
              </thead>
              <tbody>
                {perQuery.map((q) => (
                  <tr key={q.id}>
                    <td>{q.id}</td>
                    <td className="table-question">{q.question}</td>
                    <td><span className={`table-badge ${q.before.outcome_pass ? 'good' : 'bad'}`}>{q.before.outcome_pass ? 'PASS' : 'FAIL'}</span></td>
                    <td><span className={`table-badge ${q.before.trajectory_pass ? 'good' : 'bad'}`}>{q.before.trajectory_pass ? 'PASS' : 'FAIL'}</span></td>
                    <td><TagChips tags={q.before.failure_tags} /></td>
                    <td><span className={`table-badge ${q.after.outcome_pass ? 'good' : 'bad'}`}>{q.after.outcome_pass ? 'PASS' : 'FAIL'}</span></td>
                    <td><span className={`table-badge ${q.after.trajectory_pass ? 'good' : 'bad'}`}>{q.after.trajectory_pass ? 'PASS' : 'FAIL'}</span></td>
                    <td><TagChips tags={q.after.failure_tags} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Bonus: prompt injection */}
        {bonus && (
          <div className="panel-card card">
            <div className="panel-card-head" onClick={() => setBonusOpen(!bonusOpen)} style={{ cursor: 'pointer' }}>
              <span className="panel-card-title"><ShieldAlert size={15} /> Bonus: indirect prompt-injection defense</span>
              {bonusOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
            </div>
            {bonusOpen && (
              <div>
                <div className="chip-row" style={{ marginBottom: 10 }}>
                  <span className={`table-badge ${bonus.attack.undefended_context_contains_injection ? 'bad' : 'ok'}`}>
                    undefended context injected: {String(bonus.attack.undefended_context_contains_injection)}
                  </span>
                  <span className={`table-badge ${bonus.output_guardrail_demo.blocked ? 'good' : 'bad'}`}>
                    output guardrail blocked: {String(bonus.output_guardrail_demo.blocked)}
                  </span>
                  <span className="table-badge warn">
                    +{bonus.measured_overhead.added_latency_ms_per_query}ms/query overhead
                  </span>
                </div>
                <div className="agent-step-section">
                  <div className="agent-step-label">Undefended context (excerpt)</div>
                  <div className="agent-step-observation">{bonus.attack.undefended_context_excerpt}</div>
                </div>
                <div className="agent-step-section">
                  <div className="agent-step-label">Defended context (excerpt) — see residual gap noted below</div>
                  <div className="agent-step-observation">{bonus.attack.defended_context_excerpt}</div>
                </div>
                <div className="agent-step-section">
                  <div className="agent-step-label">Residual vulnerabilities</div>
                  <ul className="failure-list">
                    {bonus.residual_vulnerabilities.map((v, i) => (
                      <li key={i} className="failure-item"><div className="failure-text">{v}</div></li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
