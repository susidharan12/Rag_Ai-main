import { useCallback, useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Bot,
  Clock,
  Cpu,
  Zap,
  ChevronRight,
  ChevronDown,
  SendHorizontal,
  Sparkles,
  Timer,
  BarChart3,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  Circle,
  RefreshCw,
  Trophy,
} from 'lucide-react'
import { runAgent, fetchRaceResults } from '../api.js'

const MD_COMPONENTS = {
  table: ({ node, ...props }) => (
    <div className="table-wrap">
      <table {...props} />
    </div>
  ),
}

const TOOL_ICONS = {
  search_docs: 'search',
  get_version_info: 'layers',
  compare_versions: 'git-compare',
  get_error_info: 'alert-triangle',
  get_parameter_default: 'settings',
  finish: 'check-circle',
}

const TOOL_COLORS = {
  search_docs: '#4f46e5',
  get_version_info: '#7c3aed',
  compare_versions: '#0d9488',
  get_error_info: '#ef4444',
  get_parameter_default: '#d97706',
  check_deprecation: '#db2777',
  finish: '#10b981',
}

function StepCard({ step, index }) {
  const [expanded, setExpanded] = useState(index < 2)
  const toolColor = TOOL_COLORS[step.tool] || '#71717a'
  const isFinish = step.tool === 'finish'

  return (
    <motion.div
      className="agent-step"
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.08 }}
    >
      <div className="agent-step-header" onClick={() => setExpanded(!expanded)}>
        <div className="agent-step-number" style={{ background: toolColor }}>
          {step.step}
        </div>
        <div className="agent-step-meta">
          <div className="agent-step-tool" style={{ color: toolColor }}>
            {isFinish ? <CheckCircle2 size={13} /> : <ChevronRight size={13} />}
            {step.tool}
          </div>
          <div className="agent-step-thought">
            {step.thought.length > 80 ? step.thought.slice(0, 80) + '...' : step.thought}
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
            <div className="agent-step-section">
              <div className="agent-step-label">Chain of Thought</div>
              <div className="agent-step-thought-full">{step.thought}</div>
            </div>
            {step.args && Object.keys(step.args).length > 0 && (
              <div className="agent-step-section">
                <div className="agent-step-label">Tool Arguments</div>
                <pre className="agent-step-args">
                  {JSON.stringify(step.args, null, 2)}
                </pre>
              </div>
            )}
            <div className="agent-step-section">
              <div className="agent-step-label">Observation</div>
              <div className="agent-step-observation">{step.observation}</div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

function MetricsBar({ metrics }) {
  return (
    <div className="agent-metrics">
      <div className="agent-metric">
        <Timer size={14} />
        <span>{metrics.latency_ms.toFixed(0)}ms</span>
      </div>
      <div className="agent-metric">
        <Cpu size={14} />
        <span>{metrics.api_calls} tool calls</span>
      </div>
      <div className="agent-metric">
        <Zap size={14} />
        <span>{metrics.steps_taken} steps</span>
      </div>
      <div className="agent-metric">
        <Circle size={14} />
        <span>{metrics.stopped_by}</span>
      </div>
    </div>
  )
}

function overallWinnerLabel(w) {
  if (w === 'agent') return 'Agent'
  if (w === 'workflow') return 'Fixed Workflow'
  return 'Tie'
}

function timeAgo(iso) {
  if (!iso) return null
  const ms = Date.now() - new Date(iso).getTime()
  if (!Number.isFinite(ms) || ms < 0) return null
  const mins = Math.round(ms / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  return `${hours}h ago`
}

function RaceResults({ raceData, onRefresh, refreshing }) {
  if (!raceData) return null

  const { summary, recommendation, generated_at } = raceData
  const questionWins = summary.question_wins
  const generatedLabel = timeAgo(generated_at)

  return (
    <div className="race-results">
      <div className="race-title-row">
        <h3 className="race-title">
          <BarChart3 size={18} /> Agent vs Workflow Race
        </h3>
        <div className="race-title-actions">
          {generatedLabel && <span className="race-generated-at">Last run: {generatedLabel}</span>}
          <button
            type="button"
            className="race-refresh-btn"
            onClick={onRefresh}
            disabled={refreshing}
            title="Re-run the 10-scenario race now"
          >
            <RefreshCw size={14} className={refreshing ? 'spin' : ''} />
            {refreshing ? 'Running...' : 'Refresh'}
          </button>
        </div>
      </div>
      <p className="race-subtitle">
        This is a fixed 10-question benchmark (GitHub API + Swagger Codegen
        migration scenarios) — it does not change with whatever you ask in
        the Agent Playground. Click Refresh to re-run it.
      </p>

      {questionWins && (
        <div className={`race-overall-winner ${summary.winner.overall}`}>
          <Trophy size={16} />
          <span>
            Overall winner: <strong>{overallWinnerLabel(summary.winner.overall)}</strong>
            {' — '}
            wins {questionWins.agent}/{summary.total_questions} questions (Agent) vs{' '}
            {questionWins.workflow}/{summary.total_questions} (Workflow)
            {questionWins.tie > 0 ? `, ${questionWins.tie} tied` : ''}
          </span>
        </div>
      )}

      <div className="race-comparison">
        <div className="race-card agent-card">
          <div className="race-card-header">
            <Bot size={18} />
            <span>Agent (ReAct)</span>
          </div>
          <div className="race-card-stats">
            <div className="race-stat">
              <span className="race-stat-label">Pass Rate</span>
              <span className="race-stat-value">{(summary.agent.pass_rate * 100).toFixed(0)}%</span>
            </div>
            <div className="race-stat">
              <span className="race-stat-label">Avg Latency</span>
              <span className="race-stat-value">{summary.agent.avg_latency_ms.toFixed(0)}ms</span>
            </div>
            <div className="race-stat">
              <span className="race-stat-label">p50 / p99</span>
              <span className="race-stat-value">
                {summary.agent.p50_latency_ms.toFixed(0)} / {summary.agent.p99_latency_ms.toFixed(0)}ms
              </span>
            </div>
            <div className="race-stat">
              <span className="race-stat-label">API Calls</span>
              <span className="race-stat-value">{summary.agent.total_api_calls}</span>
            </div>
            <div className="race-stat">
              <span className="race-stat-label">Avg Steps</span>
              <span className="race-stat-value">{summary.agent.avg_steps}</span>
            </div>
            <div className="race-stat">
              <span className="race-stat-label">Est. Tokens</span>
              <span className="race-stat-value">{summary.agent.total_est_tokens}</span>
            </div>
            <div className="race-stat">
              <span className="race-stat-label">Est. Cost</span>
              <span className="race-stat-value">${summary.agent.total_est_cost_usd.toFixed(4)}</span>
            </div>
          </div>
        </div>

        <div className="race-vs">VS</div>

        <div className="race-card workflow-card">
          <div className="race-card-header">
            <Zap size={18} />
            <span>Fixed Workflow</span>
          </div>
          <div className="race-card-stats">
            <div className="race-stat">
              <span className="race-stat-label">Pass Rate</span>
              <span className="race-stat-value">{(summary.workflow.pass_rate * 100).toFixed(0)}%</span>
            </div>
            <div className="race-stat">
              <span className="race-stat-label">Avg Latency</span>
              <span className="race-stat-value">{summary.workflow.avg_latency_ms.toFixed(0)}ms</span>
            </div>
            <div className="race-stat">
              <span className="race-stat-label">p50 / p99</span>
              <span className="race-stat-value">
                {summary.workflow.p50_latency_ms.toFixed(0)} / {summary.workflow.p99_latency_ms.toFixed(0)}ms
              </span>
            </div>
            <div className="race-stat">
              <span className="race-stat-label">API Calls</span>
              <span className="race-stat-value">{summary.workflow.total_api_calls}</span>
            </div>
            <div className="race-stat">
              <span className="race-stat-label">Avg Steps</span>
              <span className="race-stat-value">{summary.workflow.avg_steps}</span>
            </div>
            <div className="race-stat">
              <span className="race-stat-label">Est. Tokens</span>
              <span className="race-stat-value">{summary.workflow.total_est_tokens}</span>
            </div>
            <div className="race-stat">
              <span className="race-stat-label">Est. Cost</span>
              <span className="race-stat-value">${summary.workflow.total_est_cost_usd.toFixed(4)}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="race-winners">
        <div className="race-winner">
          <span className="race-winner-label">Speed:</span>
          <span className={`race-winner-value ${summary.winner.speed}`}>
            {summary.winner.speed === 'workflow' ? 'Fixed Workflow' : 'Agent'} wins
          </span>
        </div>
        <div className="race-winner">
          <span className="race-winner-label">Cost:</span>
          <span className={`race-winner-value ${summary.winner.cost}`}>
            {summary.winner.cost === 'workflow' ? 'Fixed Workflow' : 'Agent'} wins
          </span>
        </div>
        <div className="race-winner">
          <span className="race-winner-label">Quality:</span>
          <span className={`race-winner-value ${summary.winner.quality}`}>
            {summary.winner.quality === 'workflow' ? 'Fixed Workflow' : 'Agent'} wins
          </span>
        </div>
      </div>

      <div className="race-recommendation">
        <TrendingUp size={15} />
        <p>{recommendation}</p>
      </div>

      <div className="race-details">
        <h4>Per-Question Breakdown</h4>
        <table className="race-table">
          <thead>
            <tr>
              <th>Q</th>
              <th>Category</th>
              <th>Agent</th>
              <th>Agent Steps</th>
              <th>Workflow</th>
              <th>Agent</th>
              <th>WF</th>
              <th>Winner</th>
            </tr>
          </thead>
          <tbody>
            {raceData.agent_results.map((ar, i) => {
              const wr = raceData.workflow_results[i]
              const winner = ar.question_winner || 'tie'
              return (
                <tr key={ar.question_id}>
                  <td>{ar.question_id}</td>
                  <td className="race-category">{ar.category}</td>
                  <td>{ar.metrics.latency_ms.toFixed(0)}ms</td>
                  <td>{ar.metrics.steps_taken}</td>
                  <td>{wr.metrics.latency_ms.toFixed(0)}ms</td>
                  <td className={ar.passed ? 'good' : 'bad'}>
                    {ar.passed ? 'PASS' : 'FAIL'} ({(ar.relevance_score * 100).toFixed(0)}%)
                  </td>
                  <td className={wr.passed ? 'good' : 'bad'}>
                    {wr.passed ? 'PASS' : 'FAIL'} ({(wr.relevance_score * 100).toFixed(0)}%)
                  </td>
                  <td
                    className={`race-question-winner ${winner}`}
                    title={ar.question_winner_reason ? `Decided by: ${ar.question_winner_reason}` : ''}
                  >
                    {overallWinnerLabel(winner)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function AgentView() {
  const [input, setInput] = useState('')
  const [pending, setPending] = useState(false)
  const [agentResult, setAgentResult] = useState(null)
  const [raceData, setRaceData] = useState(null)
  const [raceLoading, setRaceLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('playground')
  const scrollRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [agentResult])

  const handleRunAgent = async (text) => {
    const q = (text ?? input).trim()
    if (!q || pending) return
    setInput('')
    setPending(true)
    setAgentResult(null)
    try {
      const res = await runAgent(q)
      setAgentResult(res)
    } catch (e) {
      setAgentResult({
        answer: `Error: ${e.message}`,
        steps: [],
        metrics: { latency_ms: 0, api_calls: 0, tools_used: [], steps_taken: 0, stopped_by: 'error' },
        question: q,
      })
    } finally {
      setPending(false)
    }
  }

  const handleRunRace = async (force = false) => {
    setRaceLoading(true)
    try {
      const res = await fetchRaceResults(force)
      setRaceData(res)
    } catch (e) {
      console.error('Race failed:', e)
    } finally {
      setRaceLoading(false)
    }
  }

  return (
    <div className="agent-view">
      <div className="agent-tabs">
        <button
          className={`agent-tab ${activeTab === 'playground' ? 'active' : ''}`}
          onClick={() => setActiveTab('playground')}
        >
          <Bot size={14} /> Agent Playground
        </button>
        <button
          className={`agent-tab ${activeTab === 'race' ? 'active' : ''}`}
          onClick={() => setActiveTab('race')}
        >
          <BarChart3 size={14} /> Race Comparison
        </button>
      </div>

      {activeTab === 'playground' ? (
        <div className="agent-playground">
          <div className="agent-scroll" ref={scrollRef}>
            {!agentResult && !pending && (
              <div className="agent-empty">
                <div className="agent-empty-icon">
                  <Bot size={40} strokeWidth={1.5} />
                </div>
                <h3>Documentation Agent</h3>
                <p>
                  Ask a multi-step question about your indexed documents.
                  The agent will reason step-by-step using Chain of Thought
                  and pick tools to find the answer.
                </p>
                <div className="agent-suggestions">
                  {[
                    'What changed between the two versions in this documentation?',
                    'What is the default value of the main configuration option?',
                    'How do I migrate a config from the old version to the new one?',
                    'Summarize what this document covers.',
                  ].map((q) => (
                    <button
                      key={q}
                      className="agent-suggestion"
                      onClick={() => handleRunAgent(q)}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {agentResult && (
              <div className="agent-result">
                <div className="agent-question-bar">
                  <Bot size={15} />
                  <span>{agentResult.question}</span>
                </div>

                <div className="agent-steps-container">
                  {agentResult.steps.map((step, i) => (
                    <StepCard key={i} step={step} index={i} />
                  ))}
                </div>

                {pending && (
                  <div className="agent-thinking">
                    <div className="agent-thinking-dots">
                      <span /><span /><span />
                    </div>
                    <span>Agent is reasoning...</span>
                  </div>
                )}

                {agentResult.answer && (
                  <motion.div
                    className="agent-answer"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                  >
                    <div className="agent-answer-header">
                      <CheckCircle2 size={15} />
                      <span>Final Answer</span>
                    </div>
                    <div className="agent-answer-text">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
                        {agentResult.answer}
                      </ReactMarkdown>
                    </div>
                  </motion.div>
                )}

                <MetricsBar metrics={agentResult.metrics} />
              </div>
            )}

            {pending && !agentResult && (
              <div className="agent-thinking initial">
                <div className="agent-thinking-dots">
                  <span /><span /><span />
                </div>
                <span>Agent is starting...</span>
              </div>
            )}
          </div>

          <form
            className="agent-composer"
            onSubmit={(e) => { e.preventDefault(); handleRunAgent() }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask a multi-step documentation question..."
              disabled={pending}
            />
            <button type="submit" className="agent-send-btn" disabled={pending || !input.trim()}>
              {pending ? <RefreshCw size={16} className="spin" /> : <SendHorizontal size={16} />}
            </button>
          </form>
        </div>
      ) : (
        <div className="agent-race-panel">
          {!raceData && !raceLoading && (
            <div className="race-empty">
              <BarChart3 size={40} strokeWidth={1.5} />
              <h3>Agent vs Workflow Race</h3>
              <p>
                Run both approaches on 10 real migration scenarios (GitHub REST
                API version diffs + Swagger Codegen v2/v3 migration) and
                compare pass rate, speed, and cost with real numbers.
              </p>
              <button className="race-run-btn" onClick={() => handleRunRace(false)}>
                <Zap size={15} /> Run Race
              </button>
            </div>
          )}

          {raceLoading && (
            <div className="race-loading">
              <div className="agent-thinking-dots">
                <span /><span /><span />
              </div>
              <p>Running 10 scenarios through both agent and workflow...</p>
              <p className="race-loading-sub">This may take a minute or two.</p>
            </div>
          )}

          {raceData && !raceLoading && (
            <RaceResults
              raceData={raceData}
              onRefresh={() => handleRunRace(true)}
              refreshing={raceLoading}
            />
          )}
        </div>
      )}
    </div>
  )
}
