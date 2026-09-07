import { useRef, useState } from 'react'
import { motion } from 'framer-motion'
import {
  BarChart3,
  Database,
  MessageSquareText,
  Plus,
  Settings,
  Sparkles,
  Upload,
} from 'lucide-react'
import { uploadFiles } from '../api.js'

const TABS = [
  { id: 'chat', label: 'Chat', Icon: MessageSquareText },
  { id: 'analytics', label: 'Analytics', Icon: Database },
  { id: 'benchmark', label: 'Benchmark', Icon: BarChart3 },
]

export default function TopNav({
  activeView,
  onView,
  docsCount,
  onNewChat,
  onToggleDocs,
  onChanged,
  onError,
}) {
  const fileRef = useRef(null)
  const [uploading, setUploading] = useState(false)

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList).filter((f) => /\.(pdf|md|markdown|txt)$/i.test(f.name))
    if (!files.length) {
      onError?.('Only PDF, Markdown and TXT files are supported.')
      return
    }
    setUploading(true)
    try {
      for (const file of files) {
        await uploadFiles([file])
      }
      onChanged?.()
    } catch (e) {
      onError?.(e.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <header className="top-nav">
      <input
        ref={fileRef}
        type="file"
        multiple
        accept=".pdf,.md,.markdown,.txt"
        style={{ display: 'none' }}
        onChange={(e) => { if (e.target.files.length) handleFiles(e.target.files); e.target.value = '' }}
      />

      <div className="top-nav-left">
        <motion.div
          className="brand-mark"
          animate={{ boxShadow: ['0 2px 16px rgba(79,70,229,0.24)', '0 4px 26px rgba(124,58,237,0.42)', '0 2px 16px rgba(79,70,229,0.24)'] }}
          transition={{ duration: 3.2, repeat: Infinity, ease: 'easeInOut' }}
        >
          <Sparkles size={16} strokeWidth={2} />
        </motion.div>
        <div className="brand-copy">
          <div className="brand-name gradient-text">Nimbus</div>
          <div className="brand-sub">Docs Assistant</div>
        </div>
      </div>

      <nav className="top-nav-tabs">
        {TABS.map(({ id, label, Icon }) => (
          <button
            key={id}
            className={`top-nav-tab ${activeView === id ? 'active' : ''}`}
            onClick={() => onView(id)}
          >
            {activeView === id && (
              <motion.span
                layoutId="top-nav-tab-pill"
                className="top-nav-tab-pill"
                transition={{ type: 'spring', stiffness: 480, damping: 38 }}
              />
            )}
            <span className="top-nav-tab-content">
              <Icon size={14} strokeWidth={2} />
              {label}
            </span>
          </button>
        ))}
      </nav>

      <div className="top-nav-right">
        <span className="pill week-pill">Week 6</span>

        <button
          className="top-nav-btn"
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
        >
          {uploading ? <span className="spinner tiny" /> : <Upload size={14} />}
          Upload
        </button>

        <button className="top-nav-btn primary" onClick={onNewChat}>
          <Plus size={14} />
          New Chat
        </button>

        <button className="top-nav-icon-btn" title="Documents" onClick={onToggleDocs}>
          <Settings size={15} />
        </button>

        <motion.button
          className="docs-count-pill"
          onClick={onToggleDocs}
          whileTap={{ scale: 0.95 }}
        >
          {docsCount} {docsCount === 1 ? 'doc' : 'docs'}
        </motion.button>
      </div>
    </header>
  )
}
