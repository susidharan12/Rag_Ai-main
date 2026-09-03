import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import IconRail from './components/Sidebar.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import StatsPanel from './components/StatsPanel.jsx'
import AnalyticsView from './components/AnalyticsView.jsx'
import BenchmarkView from './components/BenchmarkView.jsx'
import { fetchDocuments, fetchBenchmark } from './api.js'

export default function App() {
  const [docs, setDocs] = useState([])
  const [stats, setStats] = useState(null)
  const [toast, setToast] = useState(null)
  const [activeView, setActiveView] = useState('chat')
  const [turns, setTurns] = useState([])
  const [messages, setMessages] = useState([])
  const [benchmark, setBenchmark] = useState(null)

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

  const showToast = (msg) => {
    setToast({ key: Date.now(), msg })
    setTimeout(() => setToast(null), 4200)
  }

  useEffect(() => {
    refresh()
    refreshBenchmark()
  }, [refresh, refreshBenchmark])

  const recordTurn = (turn) => setTurns((t) => [turn, ...t].slice(0, 50))

  const primaryDocName = docs[0]?.name

  return (
    <>
      <div className="app mesh-bg">
        <IconRail activeView={activeView} onView={setActiveView} />
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
              <AnalyticsView key="analytics" stats={stats} turns={turns} />
            )}
          </AnimatePresence>
        </motion.div>
        <StatsPanel
          docs={docs}
          stats={stats}
          onChanged={refresh}
          onError={showToast}
        />
      </div>
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
