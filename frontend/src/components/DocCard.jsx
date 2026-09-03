import { motion } from 'framer-motion'
import { CheckCircle2, FileCode, FileText, Trash2 } from 'lucide-react'

const STAGES = ['uploading', 'parsing', 'embedding', 'done']

export function DocCard({ doc, onDelete }) {
  const isMd = /\.md$|\.txt$/i.test(doc.name)
  const Icon = isMd ? FileCode : FileText

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 14, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, x: -30, scale: 0.95 }}
      transition={{ type: 'spring', stiffness: 380, damping: 30 }}
      className="doc-card card"
      whileHover={{ y: -2 }}
    >
      <div className="doc-row">
        <div className={`doc-icon ${isMd ? 'txt' : ''}`}>
          <Icon size={15} />
        </div>
        <div className="doc-info">
          <div className="doc-name">{doc.name}</div>
          <div className="doc-meta">
            {doc.sdk_version && <span className="meta-chip version">{doc.sdk_version}</span>}
            <span className="meta-chip">{doc.pages}p</span>
            <span className="meta-chip">{doc.chunks}c</span>
          </div>
        </div>
        <button className="doc-delete" onClick={() => onDelete(doc.doc_id)} title="Remove">
          <Trash2 size={14} />
        </button>
      </div>
    </motion.div>
  )
}

export function UploadingCard({ name, stageIndex }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 14, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ type: 'spring', stiffness: 380, damping: 30 }}
      className="doc-card card uploading"
    >
      <div className="doc-row">
        <div className={`doc-icon ${stageIndex === 3 ? 'done' : ''}`}>
          {stageIndex === 3 ? <CheckCircle2 size={15} /> : <span style={{ fontSize: 12 }}>···</span>}
        </div>
        <div className="doc-info">
          <div className="doc-name">{name}</div>
          <div className="stage-track">
            {STAGES.slice(0, 3).map((s, i) => (
              <div
                key={s}
                className={`stage-seg ${i < stageIndex ? 'done' : ''} ${i === stageIndex ? 'active' : ''}`}
              />
            ))}
          </div>
          <div className="stage-label">
            {stageIndex === 0 && 'uploading…'}
            {stageIndex === 1 && 'parsing pages…'}
            {stageIndex === 2 && 'embedding chunks…'}
            {stageIndex === 3 && 'done ✓'}
          </div>
        </div>
      </div>
    </motion.div>
  )
}
