import { motion } from 'framer-motion'
import { FileText, FileCode, Trash2 } from 'lucide-react'

const STAGES = ['uploading', 'parsing', 'embedding', 'done']

export function DocCard({ doc, onDelete }) {
  const isMd = /\.md$|\.txt$/i.test(doc.name)
  const Icon = isMd ? FileCode : FileText
  const label = isMd ? 'MD' : 'PDF'

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 14, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, x: -30, scale: 0.95 }}
      transition={{ type: 'spring', stiffness: 380, damping: 30 }}
      className="doc-card"
    >
      <div className="doc-row">
        <div className={`doc-icon ${isMd ? 'txt' : ''}`}>{label}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="doc-name">{doc.name}</div>
          <div className="doc-meta">
            {doc.sdk_version ? (
              <span className="meta-chip version">{doc.sdk_version}</span>
            ) : null}
            <span className="meta-chip">{doc.pages} pages</span>
            <span className="meta-chip">{doc.chunks} chunks</span>
          </div>
        </div>
        <button className="doc-delete" onClick={() => onDelete(doc.doc_id)} title="Remove">
          <Trash2 size={15} />
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
      className="doc-card"
    >
      <div className="doc-row">
        <div className="doc-icon">···</div>
        <div style={{ flex: 1, minWidth: 0 }}>
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
          </div>
        </div>
      </div>
    </motion.div>
  )
}
