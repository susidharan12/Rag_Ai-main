import { MessageSquareText, Database, Sparkles, BarChart3 } from 'lucide-react'

export default function IconRail({ activeView, onView }) {
  return (
    <aside className="icon-rail">
      <div className="rail-logo">
        <div className="rail-logo-icon">
          <Sparkles size={17} strokeWidth={1.8} />
        </div>
      </div>

      <nav className="rail-nav">
        <button
          title="Chat"
          className={`rail-item ${activeView === 'chat' ? 'active' : ''}`}
          onClick={() => onView('chat')}
        >
          <MessageSquareText size={18} strokeWidth={1.8} />
        </button>
        <button
          title="Analytics"
          className={`rail-item ${activeView === 'analytics' ? 'active' : ''}`}
          onClick={() => onView('analytics')}
        >
          <Database size={18} strokeWidth={1.8} />
        </button>
        <button
          title="Benchmark"
          className={`rail-item ${activeView === 'benchmark' ? 'active' : ''}`}
          onClick={() => onView('benchmark')}
        >
          <BarChart3 size={18} strokeWidth={1.8} />
        </button>
      </nav>
    </aside>
  )
}
