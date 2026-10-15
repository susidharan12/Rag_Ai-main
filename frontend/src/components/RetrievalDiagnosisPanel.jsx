import { motion } from 'framer-motion'
import { CircleSlash, Compass, FileSearch2, Gauge, ListX, Target } from 'lucide-react'

const FAILURE_META = {
  retrieval_failure: {
    label: 'Retrieval failure',
    tone: 'bad',
    Icon: Compass,
    short: 'Answer exists in the corpus but never reached the generator.',
  },
  generation_failure: {
    label: 'Generation failure',
    tone: 'warn',
    Icon: FileSearch2,
    short: "Answer was retrieved and in context - the model just didn't use it.",
  },
  not_in_corpus: {
    label: 'Not in corpus',
    tone: 'neutral',
    Icon: CircleSlash,
    short: 'Fact is not indexed anywhere - not a retrieval bug.',
  },
  over_answering: {
    label: 'Over-answering',
    tone: 'bad',
    Icon: ListX,
    short: 'Should have refused; answered instead.',
  },
}

function StatTile({ label, value, sub, icon: Icon }) {
  return (
    <div className="tile card">
      <div className="tile-icon indigo"><Icon size={16} /></div>
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  )
}

function FailureBar({ breakdown, total }) {
  const order = ['pass', 'generation_failure', 'retrieval_failure', 'over_answering', 'not_in_corpus']
  const toneClass = {
    pass: 'good',
    retrieval_failure: 'bad',
    generation_failure: 'warn',
    over_answering: 'bad',
    not_in_corpus: 'neutral',
  }
  return (
    <div className="failure-bar">
      {order.filter((k) => breakdown[k]).map((k) => (
        <div
          key={k}
          className={`failure-bar-seg ${toneClass[k]}`}
          style={{ width: `${(breakdown[k] / total) * 100}%` }}
          title={`${k}: ${breakdown[k]}`}
        />
      ))}
    </div>
  )
}

export default function RetrievalDiagnosisPanel({ data }) {
  if (!data) return null

  if (!data.available) {
    return (
      <div className="panel-card card diagnosis-unavailable">
        <div className="panel-card-head">
          <span className="panel-card-title"><Gauge size={15} /> Retrieval vs Generation Diagnosis</span>
        </div>
        <div className="empty-state">
          <CircleSlash size={16} />
          {data.reason || 'Not available yet.'}
        </div>
      </div>
    )
  }

  const { retrieval_metrics: rm, failure_breakdown: breakdown, failures, cases } = data
  const total = cases || Object.values(breakdown).reduce((a, b) => a + b, 0)

  return (
    <motion.div
      className="judge-panel card"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
    >
      <div className="judge-panel-glow" />

      <div className="judge-panel-head">
        <div className="judge-panel-title-wrap">
          <div className="judge-panel-eyebrow"><Target size={12} /> Track E · Eval Diagnosis</div>
          <h2 className="judge-panel-title">Retrieval vs Generation</h2>
          <p className="judge-panel-sub">
            For every failing case: was the answer actually retrieved (a retrieval problem),
            or was it right there in context and the generator still missed it (a generation problem)?
          </p>
        </div>
        <div className="judge-panel-badges">
          <span className="judge-stat-chip">MRR {rm.mrr ?? '–'}</span>
          <span className="judge-stat-chip accent">RRF-MRR {rm.rrf_mrr ?? '–'}</span>
        </div>
      </div>

      <div className="diagnosis-tiles">
        <StatTile label="MRR" value={rm.mrr ?? '–'} sub={`${rm.answerable_cases} answerable cases`} icon={Target} />
        <StatTile label="RRF-MRR" value={rm.rrf_mrr ?? '–'} sub="dense+lexical fusion" icon={Gauge} />
        <StatTile label="Application pass" value={`${data.application_pass}/${data.cases}`} sub={`${data.application_pass_rate}%`} icon={FileSearch2} />
        <StatTile label="Failures" value={failures.length} sub="see breakdown below" icon={Compass} />
      </div>

      <div className="judge-section-label">Failure breakdown</div>
      <FailureBar breakdown={breakdown} total={total} />
      <div className="failure-legend">
        {Object.entries(breakdown).map(([k, v]) => (
          <span key={k} className={`failure-legend-item ${FAILURE_META[k] ? FAILURE_META[k].tone : 'good'}`}>
            <i /> {k.replace(/_/g, ' ')} ({v})
          </span>
        ))}
      </div>

      {failures.length > 0 && (
        <>
          <div className="judge-section-label" style={{ marginTop: 18 }}>Why each failure happened</div>
          <div className="disagreement-list">
            {failures.map((f) => {
              const meta = FAILURE_META[f.failure_type] || FAILURE_META.generation_failure
              const Icon = meta.Icon
              return (
                <div key={f.id} className="disagreement-card diagnosis-card">
                  <div className="disagreement-head">
                    <span className="disagreement-id">{f.id} · {f.mode.replace(/_/g, ' ')}</span>
                    <span className={`table-badge ${meta.tone === 'bad' ? 'bad' : meta.tone === 'warn' ? 'warn' : 'good'}`}>
                      <Icon size={11} style={{ marginRight: 4, verticalAlign: '-2px' }} />
                      {meta.label}
                    </span>
                  </div>
                  <div className="disagreement-q">{f.question}</div>
                  <div className="disagreement-a">&ldquo;{f.answer.slice(0, 180)}{f.answer.length > 180 ? '…' : ''}&rdquo;</div>
                  <div className="diagnosis-explain">{f.explanation}</div>
                  {(f.retrieved_rank != null || f.context_hit != null) && (
                    <div className="diagnosis-meta mono">
                      {f.retrieved_rank != null && <span>retrieved rank: {f.retrieved_rank}</span>}
                      {f.rrf_rank != null && <span>RRF rank: {f.rrf_rank}</span>}
                      {f.context_hit != null && (
                        <span>in generator context: {f.context_hit ? 'yes' : 'no'}</span>
                      )}
                      {f.ground_truth_chunk_count != null && (
                        <span>chunks with the fact: {f.ground_truth_chunk_count}</span>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}
    </motion.div>
  )
}
