import { useEffect, useRef, useState } from 'react'
import { Paperclip, SendHorizontal, Sparkles, Wand2 } from 'lucide-react'
import Message from './Message.jsx'
import { askQuestion } from '../api.js'

const SUGGESTIONS = [
  'What is the default pool_size for Client.connect()?',
  'Is HTTP error code 429 retryable?',
  'How many players per side in Football (Soccer)?',
  'Show me how to verify a webhook signature in Python.',
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
        {!messages.length ? (
          <div className="hero-empty">
            <div className="hero-orb"><Sparkles size={24} /></div>
            <h2>Ask across every document</h2>
            <p>
              Upload one or more PDFs — they are parsed, chunked and embedded
              into a shared index. Answers cite the exact chunk and page they
              came from.
            </p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="suggestion-chip" onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) => <Message key={m.id} msg={m} />)
        )}
        {pending && !messages.some((m) => m.id === 'pending') && (
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
