import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Database,
  FileSearch,
  FileText,
  GitCompare,
  Layers,
  ListChecks,
  Mic,
  Paperclip,
  SendHorizontal,
  Sparkles,
  SquareCode,
  Trophy,
  Wand2,
} from 'lucide-react'
import Message from './Message.jsx'
import HeroOrb from './HeroOrb.jsx'
import { askQuestion } from '../api.js'

const LEFT_SUGGESTIONS = [
  { label: 'Summarize my documents', query: 'Summarize what these documents cover.', Icon: FileText },
  { label: 'Find specific information', query: 'What is the default timeout_ms for Client.send()?', Icon: FileSearch },
  { label: 'Compare approaches', query: 'What changed for pool_size between SDK v2 and v3?', Icon: GitCompare },
  { label: 'Explain a concept', query: 'Explain how cursor pagination works for list_events().', Icon: SquareCode },
]

const RIGHT_SUGGESTIONS = [
  { label: 'Mobile platform facts', query: 'What year was Jetpack Compose announced stable?', Icon: Layers },
  { label: 'Show a code example', query: 'Show me how to verify a webhook signature in Python.', Icon: Wand2 },
  { label: 'Check error handling', query: 'Is HTTP error code 429 retryable?', Icon: ListChecks },
  { label: 'Sports golden set', query: 'How many players per side in Football (Soccer)?', Icon: Trophy },
]

export default function ChatPanel({ hasDocs, primaryDocName, onTurn, messages, setMessages }) {
  const [input, setInput] = useState('')
  const [pending, setPending] = useState(false)
  const scrollRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, pending])

  const send = async (text) => {
    const q = (text ?? input).trim()
    if (!q || pending) return
    setInput('')
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: 'user', text: q }])
    setPending(true)
    try {
      const res = await askQuestion(q)
      setMessages((m) => [
        ...m,
        {
          id: res.trace_id,
          role: 'bot',
          text: res.answer,
          refused: res.refused,
          sources: res.sources,
          traceId: res.trace_id,
        },
      ])
      onTurn?.({
        question: q,
        traceId: res.trace_id,
        refused: !!res.refused,
        error: false,
        sources: res.sources ?? [],
        latencyMs: res.latency_ms,
        trace: res.trace,
        reason: res.refused ? (res.answer || 'Request refused') : null,
      })
    } catch (e) {
      const errMsg = `Error: ${e.message}`
      setMessages((m) => [
        ...m,
        { id: crypto.randomUUID(), role: 'bot', text: errMsg, refused: true, sources: [] },
      ])
      onTurn?.({
        question: q, traceId: null, refused: true, error: true,
        sources: [], latencyMs: null, trace: null, reason: e.message,
      })
    } finally {
      setPending(false)
    }
  }

  if (!messages.length) {
    return (
      <div className="hero-screen">
        <div className="hero-suggestions left">
          <div className="hero-suggestions-label">Suggestions</div>
          {LEFT_SUGGESTIONS.map(({ label, query, Icon }, i) => (
            <motion.button
              key={label}
              className="hero-suggestion"
              onClick={() => send(query)}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.15 + i * 0.06 }}
              whileHover={{ x: 3 }}
            >
              <span className="hero-suggestion-icon"><Icon size={15} /></span>
              {label}
            </motion.button>
          ))}
        </div>

        <div className="hero-center">
          <div className="hero-blob-wrap">
            <div className="hero-blob-glow" />
            <HeroOrb className="hero-orb-canvas" />
            <div className="hero-blob-copy">
              <div className="hero-blob-title">NIMBUS</div>
              <div className="hero-blob-sub">Ask your documents anything</div>
            </div>
          </div>

          <motion.form
            className="hero-composer"
            onSubmit={(e) => { e.preventDefault(); send() }}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.4 }}
          >
            <button type="button" className="hero-composer-icon" title="Attach">
              <Paperclip size={16} />
            </button>
            <span className="hero-composer-dot" />
            <button type="button" className="hero-composer-icon" title="Documents">
              <Database size={15} />
            </button>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask a question about your documents…"
              disabled={pending}
            />
            <button type="button" className="hero-composer-icon" title="Voice (coming soon)" disabled>
              <Mic size={15} />
            </button>
            <button type="submit" className="hero-composer-send" disabled={pending || !input.trim()}>
              {pending ? <span className="spinner tiny" /> : <SendHorizontal size={15} />}
            </button>
          </motion.form>
        </div>

        <div className="hero-suggestions right">
          <div className="hero-suggestions-label">Suggestions</div>
          {RIGHT_SUGGESTIONS.map(({ label, query, Icon }, i) => (
            <motion.button
              key={label}
              className="hero-suggestion"
              onClick={() => send(query)}
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.15 + i * 0.06 }}
              whileHover={{ x: -3 }}
            >
              <span className="hero-suggestion-icon"><Icon size={15} /></span>
              {label}
            </motion.button>
          ))}
        </div>
      </div>
    )
  }

  return (
    <>
      <header className="chat-header">
        <div className="chat-header-left">
          <div className="chat-header-title">{primaryDocName || 'Ask your documents'}</div>
          <div className="chat-header-sub">
            {messages.length} {messages.length === 1 ? 'message' : 'messages'} · RAG Assistant
          </div>
        </div>
        <div className="chat-header-right">
          <span className="pill"><span className="pill-dot" /> Online</span>
          <button className="btn-ghost" disabled>Save</button>
          <button className="btn-ghost" disabled>Export</button>
        </div>
      </header>

      <div className="msg-scroll" ref={scrollRef}>
        {messages.map((m) => <Message key={m.id} msg={m} />)}
        {pending && (
          <div className="row-msg">
            <div className="avatar"><Sparkles size={15} /></div>
            <div className="body">
              <div className="bubble">
                <div className="typing">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="composer-wrap">
        <div className="composer-toolbar">
          <button className="composer-tool"><Paperclip size={14} /> Attach</button>
          <button className="composer-tool"><Wand2 size={14} /> Enhance</button>
        </div>
        <form
          className="composer-box"
          onSubmit={(e) => { e.preventDefault(); send() }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about your documents…"
            disabled={pending}
          />
          <button type="submit" className="send-btn" disabled={pending || !input.trim()}>
            {pending ? <span className="spinner" /> : <SendHorizontal size={17} />}
          </button>
        </form>
        <div className="composer-hint">
          {hasDocs ? 'Answers cite their sources' : 'Upload a document to get started'}
        </div>
      </div>
    </>
  )
}
