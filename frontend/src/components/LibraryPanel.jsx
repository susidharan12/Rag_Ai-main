import { useCallback, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Database, UploadCloud } from 'lucide-react'
import { DocCard, UploadingCard } from './DocCard.jsx'
import { uploadFiles, deleteDocument } from '../api.js'

export default function LibraryPanel({ docs, stats, onChanged, onError }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [uploads, setUploads] = useState([])

  const handleFiles = useCallback(
    async (fileList) => {
      const files = Array.from(fileList).filter((f) =>
        /\.(pdf|md|markdown|txt)$/i.test(f.name)
      )
      if (!files.length) {
        onError('Only PDF, Markdown and TXT files are supported.')
        return
      }

      setUploads(files.map((f) => ({ name: f.name, stage: 0 })))

      for (let i = 0; i < files.length; i++) {
        setUploads((u) =>
          u.map((x, j) => (j === i ? { ...x, stage: 1 } : x))
        )
        try {
          await uploadFiles([files[i]], (_name, stage) => {
            const idx = ['uploading', 'parsing', 'embedding'].indexOf(stage)
            if (idx >= 0) {
              setUploads((u) =>
                u.map((x, j) => (j === i ? { ...x, stage: idx } : x))
              )
            }
          })
          setUploads((u) => u.map((x, j) => (j === i ? { ...x, stage: 3 } : x)))
        } catch (e) {
          onError(`${files[i].name}: ${e.message}`)
        }
      }

      setTimeout(() => setUploads([]), 700)
      onChanged()
    },
    [onChanged, onError]
  )

  return (
    <section className="panel library">
      <div className="panel-title">
        <Database /> Document Library
      </div>

      <div
        className={`dropzone ${dragging ? 'dragging' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          handleFiles(e.dataTransfer.files)
        }}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.md,.markdown,.txt"
          onChange={(e) => {
            handleFiles(e.target.files)
            e.target.value = ''
          }}
        />
        <motion.div
          className="dz-icon"
          animate={dragging ? { scale: [1, 1.15, 1] } : {}}
          transition={{ repeat: dragging ? Infinity : 0, duration: 1.1 }}
        >
          <UploadCloud size={22} />
        </motion.div>
        <div className="dz-main">Drop PDFs here or click to browse</div>
        <div className="dz-hint">Multiple files supported · also .md / .txt</div>
      </div>

      <div className="doc-list">
        <AnimatePresence initial={false}>
          {uploads.map((u) => (
            <UploadingCard key={`up-${u.name}`} name={u.name} stageIndex={u.stage} />
          ))}
          {docs.map((d) => (
            <DocCard
              key={d.doc_id}
              doc={d}
              onDelete={async (id) => {
                try {
                  await deleteDocument(id)
                  onChanged()
                } catch (e) {
                  onError(e.message)
                }
              }}
            />
          ))}
        </AnimatePresence>
        {!docs.length && !uploads.length && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 12.5, padding: '18px 8px' }}
          >
            No documents yet — upload your first PDF above.
          </motion.div>
        )}
      </div>

      <div className="library-footer">
        <span>
          corpus: <b>{stats?.chunks ?? 0}</b> chunks
        </span>
        <span>
          by version:{' '}
          <b>
            {Object.entries(stats?.by_sdk_version || {})
              .map(([k, v]) => `${k}:${v}`)
              .join(' ') || '–'}
          </b>
        </span>
      </div>
    </section>
  )
}
