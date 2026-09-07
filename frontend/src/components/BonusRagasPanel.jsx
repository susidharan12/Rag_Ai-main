import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, ChevronDown, FlaskConical, Sparkles } from 'lucide-react'

export default function BonusRagasPanel({ data }) {
  const [open, setOpen] = useState(false)
  if (!data) return null

  if (!data.available) {
    return (
      <div className="panel-card card diagnosis-unavailable">
        <div className="panel-card-head">
          <span className="panel-card-title"><FlaskConical size={15} /> Bonus · RAGAS-style Faithfulness</span>
        </div>
        <div className="empty-state">
          <AlertTriangle size={16} />
          {data.reason || 'Not available yet.'}
        </div>
      </div>
    )
  }

  const { average_faithfulness: avg, confidently_wrong_demo: demo } = data
  const pre = demo?.pre_fix_reconstruction

  const toggle = () => setOpen((o) => !o)
  const onKeyToggle = (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle() }
  }

  return (
    <motion.div
      className="insight-card card tone-3"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
    >
      <div
        className="insight-row"
        role="button"
        tabIndex={0}
        onClick={toggle}
        onKeyDown={onKeyToggle}
        aria-expanded={open}
      >
        <div className="insight-row-icon"><Sparkles size={18} /></div>
        <div className="insight-row-text">
          <div className="insight-row-eyebrow">Bonus · Not part of the 100-point rubric</div>
          <div className="insight-row-title">RAGAS-style Faithfulness + Context Precision</div>
        </div>
        <div className="insight-row-stats">
          <div className="insight-stat"><b>{avg}</b><span>avg faithfulness</span></div>
        </div>
        <ChevronDown size={18} className={`insight-chevron ${open ? 'flip' : ''}`} />
      </div>

      <AnimatePresence initial={false}>
        {open && demo && (
          <motion.div
            className="judge-panel-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
          >
            <div className="insight-divider" />
            <div className="insight-body-inner">
              <p className="judge-panel-sub" style={{ marginBottom: 16, maxWidth: 640 }}>
                Deterministic proxy (no LLM key configured) for two RAGAS ideas - see <code>eval/bonus_ragas.py</code>.
              </p>
              <div className="disagreement-card diagnosis-card">
                <div className="disagreement-head">
                  <span className="disagreement-id">Confidently, faithfully wrong</span>
                  <span className="disagreement-verdicts">
                    <span className="table-badge good">faithfulness {pre?.faithfulness_proxy ?? demo.faithfulness_proxy}</span>
                    <span className="table-badge bad">context precision {pre?.context_version_precision ?? demo.context_version_precision}</span>
                  </span>
                </div>
                <div className="disagreement-q">{demo.question}</div>
                <div className="disagreement-a">&ldquo;{pre?.answer ?? demo.answer}&rdquo;</div>
                <div className="diagnosis-explain">
                  This question resolves to <b>{demo.question_resolves_to}</b>, but the reconstructed pre-fix answer above
                  is grounded entirely in the <b>v2</b> parameter table - a chunk whose own text never says &ldquo;v2&rdquo;
                  or &ldquo;v3&rdquo; anywhere. Faithfulness alone ({pre?.faithfulness_proxy ?? demo.faithfulness_proxy}) can't
                  tell this apart from the corpus-wide average ({avg}); only context precision (or the deterministic
                  <code> api_version_stated</code> assertion) catches it.
                </div>
                <div className="diagnosis-meta mono">
                  <span>raw cosine v2 vs v3 intro chunks: near-tied (see eval/TRACK_E_REPORT.md §12)</span>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
