import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import AuroraBackground from './components/AuroraBackground.jsx'
import Header from './components/Header.jsx'
import LibraryPanel from './components/LibraryPanel.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import { fetchDocuments } from './api.js'

export default function App() {
  const [docs, setDocs] = useState([])
  const [stats, setStats] = useState(null)
  const [toast, setToast] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const data = await fetchDocuments()
      setDocs(data.documents)
      setStats(data.stats)
    } catch (e) {
      showToast(`API unreachable: ${e.message}`)
    }
  }, [])

  const showToast = (msg) => {
    setToast(msg)
    setTimeout(() => setToast(null), 4200)
  }

  useEffect(() => {
    refresh()
  }, [refresh])

  return (
    <>
      <AuroraBackground />
      <div className="shell">
        <Header stats={stats} />
        <LibraryPanel
          docs={docs}
          stats={stats}
          onChanged={refresh}
          onError={showToast}
        />
        <ChatPanel hasDocs={docs.length > 0} />
      </div>
      <AnimatePresence>
        {toast && (
          <motion.div
            className="toast-zone"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
          >
            <div className="toast">{toast}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
