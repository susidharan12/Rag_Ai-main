import { motion } from 'framer-motion'
import { ArrowRight, BadgeCheck, FlaskConical, Gauge, ShieldCheck, Sparkles, Target } from 'lucide-react'

function AgreementRing({ pct, label, tone }) {
  const r = 34
  const c = 2 * Math.PI * r
  const offset = c * (1 - pct / 100)
  return (
    <div className="agreement-ring">
      <svg width="88" height="88" viewBox="0 0 88 88">
        <circle cx="44" cy="44" r={r} fill="none" stroke="rgba(0,0,0,0.08)" strokeWidth="7" />
        <motion.circle
          cx="44" cy="44" r={r} fill="none"
          stroke={tone} strokeWidth="7" strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 0.9, ease: 'easeOut' }}
          transform="rotate(-90 44 44)"
        />
      </svg>
      <div className="agreement-ring-label">{pct}%</div>
      <span className="agreement-ring-caption">{label}</span>
    </div>
  )
}

function modeTone(rate) {
  if (rate >= 100) return 'good'
  if (rate <= 0) return 'bad'
  return 'warn'
}

function ModeBar({ mode, pass, total, rate, index }) {
  const tone = modeTone(rate)
  return (
    <motion.div
      className="mode-row"
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.035 }}
    >
      <div className="mode-row-label">
        <span>{mode.replace(/_/g, ' ')}</span>
        <b className={`mode-row-rate ${tone}`}>{pass}/{total} · {rate}%</b>
      </div>
      <div className="mode-bar">
        <motion.i
          className={tone}
          initial={{ width: 0 }}
          animate={{ width: `${rate}%` }}
          transition={{ duration: 0.6, ease: 'easeOut', delay: index * 0.035 }}
        />
      </div>
    </motion.div>
  )
}

export default function JudgeValidationPanel({ data }) {
  if (!data) return null

  const {
    cases,
    assertion_checks: assertionChecks,
    judged_criteria: judgedCriteria,
    agreement_before: before,
    agreement_after: after,
    pass_rate_by_mode: modes = [],
    disagreements = [],
    regression_cases: regressionCases = [],
    prediction,
  } = data

  const delta = after.pct - before.pct

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
          <div className="judge-panel-eyebrow"><Sparkles size={12} /> Week 6 · Task Set E</div>
          <h2 className="judge-panel-title">Docs-Answer Judge Validation</h2>
          <p className="judge-panel-sub">
            {cases} blind-labeled cases, spanning every Week&nbsp;5 failure mode &middot; labels committed to git before either judge ran
          </p>
        </div>
        <div className="judge-panel-badges">
          <span className="judge-stat-chip"><FlaskConical size={13} /> {assertionChecks} deterministic checks</span>
          <span className="judge-stat-chip accent"><ShieldCheck size={13} /> {judgedCriteria} judged criterion &middot; binary</span>
        </div>
      </div>

      <div className="judge-agreement-row">
        <AgreementRing pct={before.pct} label="Judge V1" tone="#f59e0b" />
        <div className="judge-arrow">
          <ArrowRight size={18} />
          <span className={delta >= 0 ? 'good' : 'bad'}>{delta >= 0 ? '+' : ''}{delta}pts</span>
        </div>
        <AgreementRing pct={after.pct} label="Judge V2" tone="#10b981" />
        <div className="judge-agreement-copy">
          <div className="judge-agreement-copy-title">Agreement with blind human labels</div>
          <div className="judge-agreement-copy-detail">
            {before.count}/{before.total} correct &rarr; {after.count}/{after.total} correct, after iterating the prompt on its own real V1/human disagreements.
          </div>
          {prediction?.text && (
            <div className="judge-agreement-copy-prediction">
              <Target size={12} /> {prediction.text}
            </div>
          )}
        </div>
      </div>

      <div className="judge-mode-grid">
        <div className="judge-mode-list">
          <div className="judge-section-label"><Gauge size={13} /> Pass rate by taxonomy mode</div>
          {modes.map((m, i) => <ModeBar key={m.mode} {...m} index={i} />)}
        </div>

        <div className="judge-side">
          <div className="judge-section-label"><BadgeCheck size={13} /> Verified real V1 disagreements</div>
          <div className="disagreement-list">
            {disagreements.map((d) => (
              <div key={d.id} className="disagreement-card">
                <div className="disagreement-head">
                  <span className="disagreement-id">{d.id}</span>
                  <span className="disagreement-verdicts">
                    <span className="table-badge bad">human {d.human_label}</span>
                    <span className="table-badge warn">judge {d.judge_v1}</span>
                  </span>
                </div>
                <div className="disagreement-q">{d.question}</div>
                <div className="disagreement-a">&ldquo;{d.answer}&rdquo;</div>
                {d.source && d.source !== 'hand-authored' && (
                  <div className="disagreement-source mono">verbatim trace &middot; {d.source}</div>
                )}
              </div>
            ))}
          </div>

          {regressionCases.length > 0 && (
            <div className="regression-note">
              {regressionCases.length} regression cases are verbatim real traces, not synthetic examples
            </div>
          )}
        </div>
      </div>
    </motion.div>
  )
}
