import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Bot, ChevronDown, FileText, Sparkles, User } from 'lucide-react'

function renderWithCitations(text) {
  const parts = text.split(/(\[(?:nimbus-sdk-[^:\]]+|complete-guide[^:\]]+):p\d+:c\d+\])/g)
  return parts.map((p, i) =>
    /^\[.+:p\d+:c\d+\]$/.test(p) ? (
      <span key={i} className="cite">
        {p.slice(1, -1)}
      </span>
    ) : (
      p
    )
  )
}

export function TypingDots() {
  return (
    <div className="typing">
      <i /><i /><i />
    </div>
  )
}

export default function Message({ msg }) {
  const isUser = msg.role === 'user'
  const [shown, setShown] = useState(isUser ? msg.text : '')
  const [openSnippet, setOpenSnippet] = useState(null)
  const done = !isUser && shown.length === msg.text.length

  useEffect(() => {
    if (isUser) return
    let i = 0
    const step = Math.max(2, Math.round(msg.text.length / 90))
    const t = setInterval(() => {
      i += step
      setShown(msg.text.slice(0, i))
      if (i >= msg.text.length) clearInterval(t)
    }, 14)
    return () => clearInterval(t)
  }, [msg.text, isUser])

  const sources = useMemo(() => msg.sources ?? [], [msg.sources])

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 320, damping: 28 }}
      className={`msg ${msg.role}`}
    >
      <div className={`who ${msg.role}`}>
        <span className="avatar">
          {isUser ? <User size={12} /> : <Sparkles size={12} />}
        </span>
        {isUser ? 'You' : 'Assistant'}
      </div>

      <div className={`bubble ${!isUser && msg.refused ? 'refused' : ''}`}>
        {isUser ? msg.text : renderWithCitations(shown)}
        {!isUser && !done && <TypingDots />}
      </div>

      {!isUser && done && sources.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="sources"
        >
          {sources.map((s) => (
            <button
              key={s.chunk_id}
              className="source-chip"
              onClick={() =>
                setOpenSnippet(openSnippet === s.chunk_id ? null : s.chunk_id)
              }
            >
              <FileText size={11} />
              {s.source_doc} · p{s.page_number}
              <span className="score-bar">
                <i style={{ width: `${Math.round(s.score * 100)}%` }} />
              </span>
              {s.score.toFixed(2)}
              <ChevronDown size={11} style={{ opacity: 0.6 }} />
            </button>
          ))}
        </motion.div>
      )}

      <AnimatePresence>
        {openSnippet && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            style={{ overflow: 'hidden' }}
          >
            <div className="snippet-box">
              <div className="snippet-head">
                <Bot size={13} /> {openSnippet}
              </div>
              {sources.find((s) => s.chunk_id === openSnippet)?.snippet}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {!isUser && done && msg.traceId && (
        <div className="trace-tag">trace {msg.traceId}</div>
      )}
    </motion.div>
  )
}
