import { useState } from 'react'
import {
  BarChart3,
  TrendingUp,
  Zap,
  CheckCircle2,
  AlertTriangle,
  ArrowUp,
  Download,
  Calendar,
  Layers,
  ChevronDown,
  Sparkles,
  ExternalLink
} from 'lucide-react'

const TOP_QUERIES = [
  { term: 'Remote work policy & home office allowance', count: '1,420 queries', latency: '12.4s', success: '98%', trend: '+14%' },
  { term: 'Budget approval hierarchy & Coupa workflow', count: '980 queries', latency: '8.6s', success: '96%', trend: '+8%' },
  { term: 'Snowflake analytics & dbt model documentation', count: '740 queries', latency: '6.2s', success: '94%', trend: '+22%' },
  { term: 'Company OKR scoring & Q3 cadence schedule', count: '610 queries', latency: '9.1s', success: '92%', trend: '+5%' },
  { term: 'Health insurance dental & vision enrollment', count: '520 queries', latency: '7.4s', success: '97%', trend: '-2%' },
  { term: 'Kubernetes cluster deployment guidelines', count: '480 queries', latency: '5.8s', success: '95%', trend: '+18%' }
]

const UNANSWERED_GAPS = [
  { query: 'What is our 2027 sabbatical leave policy?', count: '48 queries', confidence: '42%', action: 'Draft Policy' },
  { query: 'How to request temporary Figma Enterprise seats?', count: '34 queries', confidence: '54%', action: 'Add to FAQ' },
  { query: 'Singapore entity tax registration code', count: '29 queries', confidence: '61%', action: 'Assign to Finance' }
]

export default function AdminAnalytics() {
  const [timeRange, setTimeRange] = useState('Last 30 days')

  return (
    <>
      {/* Top Header & Range Selection */}
      <div className="sl-search-action-row">
        <div>
          <span style={{ fontSize: 13, color: '#94a3b8' }}>
            Enterprise query volume, model retrieval latency, top keyword demand, and knowledge gaps.
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            className="sl-dropdown-pill"
            onClick={() => {
              const ranges = ['Last 30 days', 'Last 7 days', 'Last 90 days', 'Year to Date']
              const next = ranges[(ranges.indexOf(timeRange) + 1) % ranges.length]
              setTimeRange(next)
            }}
          >
            <Calendar size={14} style={{ color: '#3b82f6' }} />
            <span>{timeRange}</span>
            <ChevronDown size={14} style={{ color: '#64748b' }} />
          </div>

          <button
            className="add-source-primary-btn"
            onClick={() => alert('Downloading analytics telemetry report...')}
          >
            <Download size={15} />
            <span>Export Metrics</span>
          </button>
        </div>
      </div>

      {/* 4 Summary Stats Cards */}
      <div className="sl-stats-grid">
        <div className="sl-stat-card">
          <div className="sl-stat-icon-box blue">
            <BarChart3 size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">24,850</span>
            <span className="sl-stat-label">Total Query Volume</span>
            <span className="sl-stat-subtext positive">
              <ArrowUp size={12} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 2 }} />
              18.4% this month
            </span>
          </div>
        </div>

        <div className="sl-stat-card">
          <div className="sl-stat-icon-box green">
            <Zap size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">7.2s</span>
            <span className="sl-stat-label">Median Latency</span>
            <span className="sl-stat-subtext positive">-1.4s improvement</span>
          </div>
        </div>

        <div className="sl-stat-card">
          <div className="sl-stat-icon-box blue">
            <CheckCircle2 size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">96.8%</span>
            <span className="sl-stat-label">Query Success Rate</span>
            <span className="sl-stat-subtext positive">+2.1% accuracy</span>
          </div>
        </div>

        <div className="sl-stat-card">
          <div className="sl-stat-icon-box green">
            <AlertTriangle size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">1.8%</span>
            <span className="sl-stat-label">Zero-Result Gap</span>
            <span className="sl-stat-subtext positive">Minimal knowledge gap</span>
          </div>
        </div>
      </div>

      {/* 2-Column Visualizations Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Weekly Query Activity Volume */}
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 14, padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 14, boxShadow: '0 4px 20px -2px rgba(0,0,0,0.7)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span style={{ fontSize: 15, fontWeight: 700, color: '#fff' }}>Daily Search Activity</span>
              <p style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>Average 3,550 searches per weekday</p>
            </div>
            <span style={{ color: '#10b981', fontSize: 12, fontWeight: 600 }}>Active</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', height: 160, padding: '10px 0', borderBottom: '1px solid var(--border-subtle)' }}>
            {[
              { day: 'Mon', h: 75, count: '3,810' },
              { day: 'Tue', h: 90, count: '4,200' },
              { day: 'Wed', h: 85, count: '4,050' },
              { day: 'Thu', h: 100, count: '4,620' },
              { day: 'Fri', h: 65, count: '3,100' },
              { day: 'Sat', h: 20, count: '850' },
              { day: 'Sun', h: 25, count: '940' }
            ].map((bar, idx) => (
              <div key={idx} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, flex: 1 }}>
                <span style={{ fontSize: 10, color: '#64748b' }}>{bar.count}</span>
                <div
                  style={{
                    width: '32px',
                    height: `${bar.h}%`,
                    background: bar.day === 'Thu' ? '#10b981' : '#2563eb',
                    borderRadius: '6px 6px 2px 2px',
                    transition: 'height 0.3s'
                  }}
                  title={`${bar.day}: ${bar.count}`}
                />
                <span style={{ fontSize: 11, fontWeight: 600, color: '#94a3b8' }}>{bar.day}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Source Citations Distribution */}
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 14, padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 14, boxShadow: '0 4px 20px -2px rgba(0,0,0,0.7)' }}>
          <div>
            <span style={{ fontSize: 15, fontWeight: 700, color: '#fff' }}>Knowledge Source Utilization</span>
            <p style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>Breakdown of cited enterprise documents in answers</p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 4 }}>
            {[
              { name: 'Notion Team Spaces', pct: 34, color: '#2563eb', count: '8,450 answers' },
              { name: 'Google Drive Enterprise', pct: 28, color: '#10b981', count: '6,950 answers' },
              { name: 'Slack Channels & Threads', pct: 22, color: '#3b82f6', count: '5,460 answers' },
              { name: 'Confluence Technical Wikis', pct: 16, color: '#059669', count: '3,990 answers' }
            ].map((item, idx) => (
              <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}>
                  <span style={{ color: '#e2e8f0', fontWeight: 500 }}>{item.name}</span>
                  <span style={{ color: '#94a3b8' }}>{item.pct}% ({item.count})</span>
                </div>
                <div style={{ width: '100%', height: 6, background: '#262626', borderRadius: 9999, overflow: 'hidden' }}>
                  <div style={{ width: `${item.pct}%`, height: '100%', background: item.color, borderRadius: 9999 }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Top Searched Topics Table */}
      <div className="sl-table-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span className="sl-table-header-title">Most Popular Enterprise Queries</span>
            <p style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>High-frequency search topics across the organization</p>
          </div>
          <button style={{ color: '#2563eb', fontSize: 12, fontWeight: 600 }}>Download report →</button>
        </div>

        <div className="sl-table-container">
          <table className="sl-table">
            <thead>
              <tr>
                <th>Query topic</th>
                <th>Search volume</th>
                <th>Average latency</th>
                <th>Verification score</th>
                <th>Month-over-month</th>
              </tr>
            </thead>
            <tbody>
              {TOP_QUERIES.map((q, idx) => (
                <tr key={idx}>
                  <td style={{ fontWeight: 600, color: '#f8fafc' }}>{q.term}</td>
                  <td>{q.count}</td>
                  <td><span style={{ fontFamily: 'monospace', color: '#38bdf8' }}>{q.latency}</span></td>
                  <td><span className="status-badge-healthy">{q.success}</span></td>
                  <td><span style={{ color: q.trend.startsWith('+') ? '#10b981' : '#64748b', fontWeight: 600 }}>{q.trend}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Knowledge Gap Alerts */}
      <div className="sl-table-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span className="sl-table-header-title">Knowledge Gap Alert Queue</span>
            <p style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>
              Questions asked by employees where answer confidence was low (&lt;70%). Draft documentation to resolve.
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 4 }}>
          {UNANSWERED_GAPS.map((gap, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '12px 14px',
                background: 'var(--bg-app)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 8
              }}
            >
              <div>
                <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: 13.5 }}>{gap.query}</div>
                <div style={{ fontSize: 11.5, color: '#64748b', marginTop: 2 }}>
                  Asked {gap.count} • Retrieval confidence was only {gap.confidence}
                </div>
              </div>

              <button
                style={{
                  background: '#2563eb',
                  color: '#fff',
                  fontSize: 12,
                  fontWeight: 600,
                  padding: '6px 12px',
                  borderRadius: 6
                }}
                onClick={() => alert(`Creating draft documentation task for "${gap.query}"`)}
              >
                {gap.action}
              </button>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
