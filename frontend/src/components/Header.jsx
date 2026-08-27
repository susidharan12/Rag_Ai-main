import { BookOpenCheck } from 'lucide-react'

export default function Header({ stats }) {
  return (
    <header className="header">
      <div className="logo-ring">
        <BookOpenCheck size={22} strokeWidth={2.2} />
      </div>
      <div>
        <h1>RAG Docs Assistant</h1>
        <div className="sub">Multi-document RAG · every answer traced</div>
      </div>
      <div className="header-stats">
        <div className="stat-pill">
          <span className="stat-dot" />
          online
        </div>
        <div className="stat-pill">
          docs <b>{stats?.documents ?? '–'}</b>
        </div>
        <div className="stat-pill">
          chunks <b>{stats?.chunks ?? '–'}</b>
        </div>
      </div>
    </header>
  )
}
