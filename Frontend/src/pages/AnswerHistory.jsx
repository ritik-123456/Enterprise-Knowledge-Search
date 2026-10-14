import { useState } from 'react'
import {
  Search,
  Clock,
  Zap,
  ThumbsUp,
  ThumbsDown,
  Bookmark,
  ChevronDown,
  Download,
  Filter,
  CheckCircle2,
  ExternalLink,
  X,
  Sparkles
} from 'lucide-react'
import { AVATARS } from '../components/BrandIcons'

const HISTORY_DATA = [
  {
    id: 'h-1',
    query: 'What is our remote work policy?',
    askedBy: 'Olivia Rhye',
    dept: 'Product',
    time: 'Today at 10:24 AM',
    latency: '12.4s',
    confidence: '92%',
    sourcesCount: 7,
    feedback: 'good',
    bookmarked: true,
    summary: "Employees can work remotely up to 3 days per week with core collaboration hours between 10 AM – 3 PM local time.",
    sourcesCited: ['#company-policy (Slack)', 'Employee Handbook (Notion)', 'Workplace Guidelines.pdf (Drive)']
  },
  {
    id: 'h-2',
    query: 'How do I request budget approval?',
    askedBy: 'Olivia Rhye',
    dept: 'Product',
    time: 'Yesterday at 3:15 PM',
    latency: '8.6s',
    confidence: '96%',
    sourcesCount: 5,
    feedback: 'good',
    bookmarked: true,
    summary: 'Purchases under $5,000 require manager approval via Ramp or Coupa. Over $5,000 requires Department VP signoff.',
    sourcesCited: ['Procurement-Matrix-2026.pdf (Drive)', 'Finance Approval Hierarchy (Notion)', '#finance-helpdesk (Slack)']
  },
  {
    id: 'h-3',
    query: 'What tools do we use for analytics?',
    askedBy: 'Liam Chen',
    dept: 'Engineering',
    time: 'Oct 8 at 11:00 AM',
    latency: '6.2s',
    confidence: '94%',
    sourcesCount: 9,
    feedback: 'good',
    bookmarked: false,
    summary: 'PostHog & Segment for telemetry, Snowflake as enterprise warehouse, dbt for transforms, Metabase for executive dashboards.',
    sourcesCited: ['Data Stack Architecture (Docs)', '#data-announcements (Slack)', 'Analytics Tooling Matrix (Drive)']
  },
  {
    id: 'h-4',
    query: 'Where can I find the OKR process?',
    askedBy: 'Noah Levin',
    dept: 'Finance',
    time: 'Oct 5 at 4:40 PM',
    latency: '9.1s',
    confidence: '91%',
    sourcesCount: 6,
    feedback: null,
    bookmarked: false,
    summary: 'Company-wide OKRs are drafted 3 weeks before quarter end and tracked in our centralized Notion OKR Hub and Jira Align.',
    sourcesCited: ['Company OKR Hub 2026 (Notion)', '#all-company-okrs (Slack)', 'Executive Strategy Deck (Drive)']
  },
  {
    id: 'h-5',
    query: 'What are the travel reimbursement meal limits?',
    askedBy: 'Emma Davis',
    dept: 'HR',
    time: 'Oct 3 at 2:10 PM',
    latency: '7.8s',
    confidence: '95%',
    sourcesCount: 4,
    feedback: 'good',
    bookmarked: false,
    summary: 'Daily per-diem allowance is capped at $75/day for domestic travel and $110/day for high-cost international metros.',
    sourcesCited: ['Travel & Expense Policy 2026 (Drive)', 'Finance FAQ (Notion)']
  },
  {
    id: 'h-6',
    query: 'How to provision staging AWS credentials?',
    askedBy: 'Liam Chen',
    dept: 'Engineering',
    time: 'Oct 1 at 9:30 AM',
    latency: '5.9s',
    confidence: '88%',
    sourcesCount: 5,
    feedback: 'good',
    bookmarked: true,
    summary: 'Request temporary IAM assume-role via Teleport or run `aws-sso login` through our Okta enterprise connector.',
    sourcesCited: ['AWS Multi-Account Strategy (Wikis)', 'Infra Access Runbook (Confluence)']
  }
]

export default function AnswerHistory() {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedDeptFilter, setSelectedDeptFilter] = useState('All departments')
  const [selectedFeedbackFilter, setSelectedFeedbackFilter] = useState('All feedback')
  const [activeItem, setActiveItem] = useState(null)
  const [historyList, setHistoryList] = useState(HISTORY_DATA)

  const filteredHistory = historyList.filter((item) => {
    if (selectedDeptFilter !== 'All departments' && item.dept !== selectedDeptFilter) return false
    if (selectedFeedbackFilter === 'Positive only' && item.feedback !== 'good') return false
    if (selectedFeedbackFilter === 'Bookmarked only' && !item.bookmarked) return false
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      const matchQ = item.query.toLowerCase().includes(q)
      const matchBy = item.askedBy.toLowerCase().includes(q)
      const matchSum = item.summary.toLowerCase().includes(q)
      if (!matchQ && !matchBy && !matchSum) return false
    }
    return true
  })

  const toggleBookmark = (id, e) => {
    e.stopPropagation()
    setHistoryList(list =>
      list.map(item => item.id === id ? { ...item, bookmarked: !item.bookmarked } : item)
    )
  }

  return (
    <>
      {/* Top Search & Export Action */}
      <div className="sl-search-action-row">
        <div className="sl-search-box">
          <Search size={16} style={{ color: '#64748b' }} />
          <input
            type="text"
            className="sl-search-input"
            placeholder="Search through past answers, questions, or users..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <button
          className="add-source-primary-btn"
          onClick={() => alert('Exporting sanitized audit log as CSV...')}
        >
          <Download size={16} />
          <span>Export Audit Log</span>
        </button>
      </div>

      {/* 4 Stats Cards */}
      <div className="sl-stats-grid">
        <div className="sl-stat-card">
          <div className="sl-stat-icon-box blue">
            <Clock size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">1,248</span>
            <span className="sl-stat-label">Total Answers Generated</span>
            <span className="sl-stat-subtext positive">+18% this month</span>
          </div>
        </div>

        <div className="sl-stat-card">
          <div className="sl-stat-icon-box green">
            <Zap size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">8.4s</span>
            <span className="sl-stat-label">Median Latency</span>
            <span className="sl-stat-subtext positive">Fast retrieval</span>
          </div>
        </div>

        <div className="sl-stat-card">
          <div className="sl-stat-icon-box green">
            <CheckCircle2 size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">97.4%</span>
            <span className="sl-stat-label">Satisfaction Rate</span>
            <span className="sl-stat-subtext positive">High team trust</span>
          </div>
        </div>

        <div className="sl-stat-card">
          <div className="sl-stat-icon-box blue">
            <Bookmark size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">42</span>
            <span className="sl-stat-label">Bookmarked Answers</span>
            <span className="sl-stat-subtext">Saved by team</span>
          </div>
        </div>
      </div>

      {/* Filters Row */}
      <div className="sl-filters-row">
        <div className="sl-dropdown-group">
          <div
            className="sl-dropdown-pill"
            onClick={() => {
              const depts = ['All departments', 'Product', 'Engineering', 'Finance', 'HR']
              const next = depts[(depts.indexOf(selectedDeptFilter) + 1) % depts.length]
              setSelectedDeptFilter(next)
            }}
          >
            <span>{selectedDeptFilter}</span>
            <ChevronDown size={14} style={{ color: '#64748b' }} />
          </div>

          <div
            className="sl-dropdown-pill"
            onClick={() => {
              const options = ['All feedback', 'Positive only', 'Bookmarked only']
              const next = options[(options.indexOf(selectedFeedbackFilter) + 1) % options.length]
              setSelectedFeedbackFilter(next)
            }}
          >
            <span>{selectedFeedbackFilter}</span>
            <ChevronDown size={14} style={{ color: '#64748b' }} />
          </div>
        </div>

        <button
          className="sl-filters-btn"
          onClick={() => {
            setSelectedDeptFilter('All departments')
            setSelectedFeedbackFilter('All feedback')
            setSearchQuery('')
          }}
        >
          <Filter size={14} />
          <span>Reset Filters</span>
        </button>
      </div>

      {/* History Table Card */}
      <div className="sl-table-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="sl-table-header-title">Audit History ({filteredHistory.length} logs)</span>
          <span style={{ fontSize: 12, color: '#64748b' }}>Click any query to view full response & citations</span>
        </div>

        <div className="sl-table-container">
          <table className="sl-table">
            <thead>
              <tr>
                <th>Question asked</th>
                <th>User</th>
                <th>Department</th>
                <th>Latency</th>
                <th>Confidence</th>
                <th>Sources</th>
                <th>Timestamp</th>
                <th style={{ textAlign: 'center' }}>Saved</th>
              </tr>
            </thead>
            <tbody>
              {filteredHistory.map((item) => (
                <tr
                  key={item.id}
                  onClick={() => setActiveItem(item)}
                  style={{ cursor: 'pointer' }}
                >
                  <td>
                    <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: 13.5 }}>
                      {item.query}
                    </div>
                    <div style={{ fontSize: 11.5, color: '#94a3b8', marginTop: 2, display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                      {item.summary}
                    </div>
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <img
                        src={AVATARS[item.askedBy] || AVATARS['Olivia Rhye']}
                        alt={item.askedBy}
                        style={{ width: 22, height: 22, borderRadius: '50%' }}
                      />
                      <span>{item.askedBy}</span>
                    </div>
                  </td>
                  <td>
                    <span style={{ fontSize: 11.5, color: '#94a3b8' }}>{item.dept}</span>
                  </td>
                  <td>
                    <span style={{ fontFamily: 'monospace', color: '#38bdf8' }}>{item.latency}</span>
                  </td>
                  <td>
                    <span className="status-badge-healthy">{item.confidence}</span>
                  </td>
                  <td>
                    <span style={{ color: '#94a3b8' }}>{item.sourcesCount} sources</span>
                  </td>
                  <td>
                    <span style={{ color: '#64748b', fontSize: 11.5 }}>{item.time}</span>
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <button
                      onClick={(e) => toggleBookmark(item.id, e)}
                      style={{ color: item.bookmarked ? '#2563eb' : '#475569' }}
                    >
                      <Bookmark size={16} fill={item.bookmarked ? '#2563eb' : 'none'} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Answer Preview Modal */}
      {activeItem && (
        <div className="modal-overlay" onClick={() => setActiveItem(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Sparkles size={18} style={{ color: '#3b82f6' }} />
                <span className="modal-title">{activeItem.query}</span>
              </div>
              <button onClick={() => setActiveItem(null)} style={{ color: '#94a3b8' }}>
                <X size={20} />
              </button>
            </div>

            <div style={{ display: 'flex', gap: 14, fontSize: 12, color: '#94a3b8' }}>
              <span>Asked by: <strong style={{ color: '#fff' }}>{activeItem.askedBy}</strong></span>
              <span>Time: <strong style={{ color: '#fff' }}>{activeItem.time}</strong></span>
              <span>Confidence: <strong style={{ color: '#10b981' }}>{activeItem.confidence}</strong></span>
            </div>

            <div style={{ background: 'var(--bg-app)', border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 16 }}>
              <div style={{ fontSize: 13.5, color: '#e2e8f0', lineHeight: 1.6 }}>
                {activeItem.summary}
              </div>

              <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border-subtle)' }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>
                  Cited Sources ({activeItem.sourcesCited.length})
                </span>
                <ul style={{ paddingLeft: 16, marginTop: 6, display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: '#94a3b8' }}>
                  {activeItem.sourcesCited.map((s, idx) => (
                    <li key={idx} style={{ color: '#38bdf8' }}>{s}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#64748b' }}>
                <span>User Rating:</span>
                <span style={{ color: '#10b981', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <ThumbsUp size={13} /> Positive
                </span>
              </div>

              <button
                className="add-source-primary-btn"
                onClick={() => {
                  navigator.clipboard.writeText(`${activeItem.query}\n\n${activeItem.summary}`)
                  alert('Copied to clipboard!')
                }}
              >
                <span>Copy Response</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
