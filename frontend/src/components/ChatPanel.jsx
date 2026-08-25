import { useEffect, useRef, useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import { MessagesSquare, SendHorizontal } from 'lucide-react'
import Message, { TypingDots } from './Message.jsx'
import { askQuestion } from '../api.js'

const SUGGESTIONS = [
  'What is the default pool_size for Client.connect()?',
  'Is HTTP error code 429 retryable?',
  'How many players per side in Football (Soccer)?',
  'Show me how to verify a webhook signature in Python.',
]

export default function ChatPanel({ hasDocs }) {
  const [messages, setMessages] = useState([])
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
    } catch (e) {
      setMessages((m) => [
        ...m,
        { id: crypto.randomUUID(), role: 'bot', text: `Error: ${e.message}`, refused: true, sources: [] },
      ])
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="panel chat">
      <div className="panel-title">
        <MessagesSquare /> Ask the corpus
      </div>

      <div className="msg-scroll" ref={scrollRef}>
        {!messages.length ? (
          <div className="hero-empty">
            <div className="hero-orb">
              <div>
                <svg width="30" height="30" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                  <circle cx="11" cy="11" r="7" />
                  <path d="M20 20l-3.2-3.2" />
                  <path d="M8.5 11h5M11 8.5v5" />
                </svg>
              </div>
            </div>
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
            {!hasDocs && (
              <p style={{ fontSize: 12.5, color: 'var(--text-3)' }}>
                Tip: upload a document in the library first.
              </p>
            )}
          </div>
        ) : (
          messages.map((m) => <Message key={m.id} msg={m} />)
        )}
        {pending && !messages.some((m) => m.id === 'pending') && (
          <div className="msg bot">
            <div className="who bot">Assistant</div>
            <div className="bubble">
              <TypingDots />
            </div>
          </div>
        )}
      </div>

      <div className="composer">
        <form
          className="composer-box"
          onSubmit={(e) => {
            e.preventDefault()
            send()
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about your documents…"
            disabled={pending}
          />
          <button type="submit" className="send-btn" disabled={pending || !input.trim()}>
            {pending ? (
              <span className="spinner" />
            ) : (
              <SendHorizontal size={17} />
            )}
          </button>
        </form>
      </div>
    </section>
  )
}
