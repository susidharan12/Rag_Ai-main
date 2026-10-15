import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X } from 'lucide-react'
import TopNav from './components/TopNav.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import StatsPanel from './components/StatsPanel.jsx'
import AnalyticsView from './components/AnalyticsView.jsx'
import BenchmarkView from './components/BenchmarkView.jsx'
import { fetchDocuments, fetchBenchmark, fetchJudgeEval, fetchTrackEEval } from './api.js'

export default function App() {
  const [docs, setDocs] = useState([])
  const [stats, setStats] = useState(null)
  const [toast, setToast] = useState(null)
  const [activeView, setActiveView] = useState('chat')
  const [turns, setTurns] = useState([])
  const [messages, setMessages] = useState([])
  const [benchmark, setBenchmark] = useState(null)
  const [judgeEval, setJudgeEval] = useState(null)
  const [trackEEval, setTrackEEval] = useState(null)
  const [docsOpen, setDocsOpen] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const data = await fetchDocuments()
      setDocs(data.documents)
      setStats(data.stats)
    } catch (e) {
      showToast(`API unreachable: ${e.message}`)
    }
  }, [])

  const refreshBenchmark = useCallback(async () => {
    try {
      const data = await fetchBenchmark()
      setBenchmark(data)
    } catch (e) {
      showToast(`Benchmark unavailable: ${e.message}`)
    }
  }, [])

  const refreshJudgeEval = useCallback(async () => {
    try {
      const data = await fetchJudgeEval()
      setJudgeEval(data)
    } catch (e) {
      showToast(`Judge eval unavailable: ${e.message}`)
    }
  }, [])

  const refreshTrackEEval = useCallback(async () => {
    try {
      const data = await fetchTrackEEval()
      setTrackEEval(data)
    } catch (e) {
      showToast(`Track E eval unavailable: ${e.message}`)
    }
  }, [])

  const showToast = (msg) => {
    setToast({ key: Date.now(), msg })
    setTimeout(() => setToast(null), 4200)
  }

  useEffect(() => {
    refresh()
    refreshBenchmark()
    refreshJudgeEval()
    refreshTrackEEval()
  }, [refresh, refreshBenchmark, refreshJudgeEval, refreshTrackEEval])

  const recordTurn = (turn) => setTurns((t) => [turn, ...t].slice(0, 50))

  const primaryDocName = docs[0]?.name

  return (
    <>
      <div className="app mesh-bg">
        <TopNav
          activeView={activeView}
          onView={setActiveView}
          docsCount={docs.length}
          onNewChat={() => setMessages([])}
          onToggleDocs={() => setDocsOpen((o) => !o)}
          onChanged={refresh}
          onError={showToast}
        />

        <div className="app-body">
          <motion.div
            className="main-col"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
          >
            <AnimatePresence mode="wait">
              {activeView === 'chat' ? (
                <ChatPanel
                  key="chat"
                  hasDocs={docs.length > 0}
                  primaryDocName={primaryDocName}
                  onTurn={recordTurn}
                  messages={messages}
                  setMessages={setMessages}
                />
              ) : activeView === 'benchmark' ? (
                <BenchmarkView key="benchmark" benchmark={benchmark} turns={turns} />
              ) : (
                <AnalyticsView key="analytics" stats={stats} turns={turns} judgeEval={judgeEval} trackEEval={trackEEval} />
              )}
            </AnimatePresence>
          </motion.div>
        </div>

        <div className="brand-avatar" title="Nimbus">N</div>
      </div>

      <AnimatePresence>
        {docsOpen && (
          <>
            <motion.div
              key="docs-backdrop"
              className="drawer-backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setDocsOpen(false)}
            />
            <motion.div
              key="docs-drawer"
              className="docs-drawer"
              initial={{ x: 320, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 320, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 340, damping: 34 }}
            >
              <button className="docs-drawer-close" onClick={() => setDocsOpen(false)}>
                <X size={16} />
              </button>
              <StatsPanel
                docs={docs}
                stats={stats}
                onChanged={refresh}
                onError={showToast}
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {toast && (
          <motion.div
            key={toast.key}
            className="toast-zone"
            initial={{ opacity: 0, y: 20, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.9 }}
            transition={{ type: 'spring', stiffness: 400, damping: 28 }}
          >
            <div className="toast">{toast.msg}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
