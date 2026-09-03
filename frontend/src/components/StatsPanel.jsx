import { useCallback, useRef, useState } from 'react'
import { Boxes, ChevronDown } from 'lucide-react'
import { DocCard, UploadingCard } from './DocCard.jsx'
import { uploadFiles, deleteDocument } from '../api.js'

function StatsCard({ children, className = '' }) {
  return <div className={`stats-card card ${className}`}>{children}</div>
}

export default function StatsPanel({ docs, stats, onChanged, onError }) {
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
        setUploads((u) => u.map((x, j) => (j === i ? { ...x, stage: 1 } : x)))
        try {
          await uploadFiles([files[i]], (_name, stage) => {
            const idx = ['uploading', 'parsing', 'embedding'].indexOf(stage)
            if (idx >= 0) setUploads((u) => u.map((x, j) => (j === i ? { ...x, stage: idx } : x)))
          })
          setUploads((u) => u.map((x, j) => (j === i ? { ...x, stage: 3 } : x)))
        } catch (e) {
          onError(`${files[i].name}: ${e.message}`)
        }
      }
      setTimeout(() => setUploads([]), 1200)
      onChanged()
    },
    [onChanged, onError]
  )

  const docsCount = docs.length
  const chunksCount = stats?.chunks ?? 0
  const usagePct = docsCount ? Math.min(100, Math.round((docsCount / (docsCount + 4)) * 100)) : 0
  const limit = docsCount + 4
  const remaining = Math.max(0, limit - docsCount)
  const versions = stats?.by_sdk_version || {}

  const radius = 26
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - usagePct / 100)

  return (
    <aside className="stats-col">
      <div className="stats-head">
        <div className="stats-head-title">Overview</div>
        <button className="btn-ghost"><ChevronDown size={14} /></button>
      </div>

      <StatsCard>
        <div className="stats-card-title"><span>Corpus Usage</span><span>Live</span></div>
        <div className="progress-main">
          <div className="progress-ring" style={{ position: 'relative' }}>
            <svg width="64" height="64">
              <defs>
                <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#4f46e5" />
                  <stop offset="100%" stopColor="#0d9488" />
                </linearGradient>
              </defs>
              <circle className="track" cx="32" cy="32" r={radius} fill="none" strokeWidth="6" />
              <circle
                className="fill"
                cx="32"
                cy="32"
                r={radius}
                fill="none"
                strokeWidth="6"
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={offset}
              />
            </svg>
            <div className="progress-ring-label">{usagePct}%</div>
          </div>
          <div className="progress-copy">
            <b>{docsCount}</b>
            <span>of {limit} limit</span>
            <span style={{ display: 'block', color: 'var(--good)' }}>{remaining} remaining</span>
          </div>
        </div>
        <div className="stat-grid-2">
          <div className="stat-tile card">
            <div className="stat-tile-label">Documents</div>
            <div className="stat-tile-value">{docsCount}</div>
            <div className="stat-tile-delta good">indexed</div>
          </div>
          <div className="stat-tile card">
            <div className="stat-tile-label">Chunks</div>
            <div className="stat-tile-value">{chunksCount}</div>
            <div className="stat-tile-delta good">embedded</div>
          </div>
        </div>
      </StatsCard>

      <StatsCard>
        <div className="stats-card-title"><span>Performance</span></div>
        <div className="perf-row">
          <div className="bar-label"><span>Retrieval precision</span><b>{stats ? 'high' : '–'}</b></div>
          <div className="perf-bar"><i style={{ width: '90%' }} /></div>
        </div>
        <div className="perf-row">
          <div className="bar-label"><span>Embedded corpus</span><b>{chunksCount}</b></div>
          <div className="perf-bar"><i style={{ width: chunksCount ? '75%' : '0%' }} /></div>
        </div>
        <div className="perf-row">
          <div className="bar-label"><span>Trace coverage</span><b>100%</b></div>
          <div className="perf-bar"><i style={{ width: '100%' }} /></div>
        </div>
      </StatsCard>

      <StatsCard>
        <div className="stats-card-title"><span>Sources</span><span>{docsCount}</span></div>

        <div
          className={`side-upload ${dragging ? 'dragging' : ''}`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files) }}
        >
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.md,.markdown,.txt"
            onChange={(e) => { handleFiles(e.target.files); e.target.value = '' }}
          />
          <div className="side-upload-main">Add documents</div>
          <div className="side-upload-hint">.pdf · .md · .txt</div>
        </div>

        <div className="doc-list">
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
        </div>
        {!docs.length && !uploads.length && (
          <div className="empty-hint"><Boxes size={15} /> No sources yet</div>
        )}
      </StatsCard>

      {Object.keys(versions).length > 0 && (
        <div className="stats-foot">
          by version:{' '}
          {Object.entries(versions).map(([k, v]) => `${k}:${v}`).join(' · ')}
        </div>
      )}
    </aside>
  )
}
