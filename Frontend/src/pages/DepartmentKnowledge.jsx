import { useState } from 'react'
import {
  FolderGit2,
  Users,
  Search,
  BookOpen,
  FileText,
  Clock,
  ExternalLink,
  Shield,
  Plus,
  X,
  Eye,
  CheckCircle2,
  Layers
} from 'lucide-react'
import { AVATARS } from '../components/BrandIcons'

const DEPARTMENTS = [
  {
    id: 'eng',
    name: 'Engineering & DevOps',
    tag: 'Engineering',
    docCount: '4,210 artifacts',
    storage: '6.4 GB',
    coverage: '98%',
    lead: 'Liam Chen',
    lastSync: '10 min ago',
    pinnedDocs: [
      { name: 'Kubernetes Cluster Production Runbook', type: 'Confluence', updated: 'Yesterday', views: 840 },
      { name: 'Microservices Architecture RFC & Schema', type: 'Notion', updated: '3 days ago', views: 1220 },
      { name: 'Secret & Key Management Guidelines', type: 'Wikis', updated: '1 week ago', views: 610 }
    ]
  },
  {
    id: 'hr',
    name: 'People Operations & HR',
    tag: 'HR',
    docCount: '1,890 artifacts',
    storage: '2.8 GB',
    coverage: '96%',
    lead: 'Emma Davis',
    lastSync: '1 hour ago',
    pinnedDocs: [
      { name: '2026 Remote Work & Hybrid Work Policy', type: 'Google Drive', updated: 'Today', views: 3410 },
      { name: 'Global Health & Dental Benefits Guide', type: 'SharePoint', updated: '2 days ago', views: 1890 },
      { name: 'Annual Performance Review Milestones', type: 'Notion', updated: '5 days ago', views: 980 }
    ]
  },
  {
    id: 'product',
    name: 'Product & UX Design',
    tag: 'Product',
    docCount: '2,940 artifacts',
    storage: '4.2 GB',
    coverage: '94%',
    lead: 'Olivia Rhye',
    lastSync: '25 min ago',
    pinnedDocs: [
      { name: 'Design System Tokens & Accessibility Specs', type: 'Notion', updated: 'Today', views: 2450 },
      { name: 'Q3 Product Strategy Roadmap & PRDs', type: 'Confluence', updated: '3 days ago', views: 1670 },
      { name: 'Customer Journey Funnel Analysis 2026', type: 'Google Drive', updated: '1 week ago', views: 890 }
    ]
  },
  {
    id: 'finance',
    name: 'Finance & Procurement',
    tag: 'Finance',
    docCount: '1,420 artifacts',
    storage: '1.9 GB',
    coverage: '91%',
    lead: 'Noah Levin',
    lastSync: '3 hours ago',
    pinnedDocs: [
      { name: 'Procurement Delegation of Authority Matrix', type: 'Google Drive', updated: 'Yesterday', views: 1120 },
      { name: 'Travel & Expense Reimbursement Policy', type: 'Notion', updated: '4 days ago', views: 1450 },
      { name: 'Annual SaaS Vendor Audit Catalog', type: 'SharePoint', updated: '2 weeks ago', views: 520 }
    ]
  },
  {
    id: 'legal',
    name: 'Legal & Compliance',
    tag: 'Legal',
    docCount: '840 artifacts',
    storage: '1.2 GB',
    coverage: '89%',
    lead: 'Emma Davis',
    lastSync: 'Yesterday',
    pinnedDocs: [
      { name: 'SOC2 Type II Audit & Security Attestation', type: 'PDF Documents', updated: '3 days ago', views: 760 },
      { name: 'Enterprise Data Privacy Addendum (DPA)', type: 'Google Drive', updated: '1 week ago', views: 490 },
      { name: 'Master Services Agreement (MSA) Template', type: 'SharePoint', updated: '2 weeks ago', views: 630 }
    ]
  },
  {
    id: 'cs',
    name: 'Customer Success & Support',
    tag: 'Support',
    docCount: '3,520 artifacts',
    storage: '3.6 GB',
    coverage: '95%',
    lead: 'Olivia Rhye',
    lastSync: '40 min ago',
    pinnedDocs: [
      { name: 'Enterprise Tier 1 Incident Playbook', type: 'Wikis', updated: 'Yesterday', views: 2100 },
      { name: 'Customer Onboarding Milestone Checklist', type: 'Notion', updated: '2 days ago', views: 1540 },
      { name: 'SLA Escalation Matrix & On-call Roster', type: 'Confluence', updated: '6 days ago', views: 820 }
    ]
  }
]

export default function DepartmentKnowledge() {
  const [selectedTag, setSelectedTag] = useState('All')
  const [searchQuery, setSearchQuery] = useState('')
  const [activePreviewDoc, setActivePreviewDoc] = useState(null)

  const filteredDepts = DEPARTMENTS.filter((d) => {
    if (selectedTag !== 'All' && d.tag !== selectedTag) return false
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      const matchName = d.name.toLowerCase().includes(q)
      const matchDocs = d.pinnedDocs.some(doc => doc.name.toLowerCase().includes(q))
      if (!matchName && !matchDocs) return false
    }
    return true
  })

  return (
    <>
      {/* Top Header Controls */}
      <div className="sl-search-action-row">
        <div className="sl-search-box">
          <Search size={16} style={{ color: '#64748b' }} />
          <input
            type="text"
            className="sl-search-input"
            placeholder="Search department spaces, runbooks, policies..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <button className="add-source-primary-btn" onClick={() => alert('Add new department space')}>
          <Plus size={16} />
          <span>New Knowledge Space</span>
        </button>
      </div>

      {/* 4 Summary Cards */}
      <div className="sl-stats-grid">
        <div className="sl-stat-card">
          <div className="sl-stat-icon-box blue">
            <FolderGit2 size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">6</span>
            <span className="sl-stat-label">Active Spaces</span>
            <span className="sl-stat-subtext positive">100% Connected</span>
          </div>
        </div>

        <div className="sl-stat-card">
          <div className="sl-stat-icon-box green">
            <FileText size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">14,820</span>
            <span className="sl-stat-label">Indexed Documents</span>
            <span className="sl-stat-subtext positive">+320 this week</span>
          </div>
        </div>

        <div className="sl-stat-card">
          <div className="sl-stat-icon-box blue">
            <CheckCircle2 size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">94.2%</span>
            <span className="sl-stat-label">Knowledge Depth</span>
            <span className="sl-stat-subtext">Semantic Index</span>
          </div>
        </div>

        <div className="sl-stat-card">
          <div className="sl-stat-icon-box green">
            <Users size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">142</span>
            <span className="sl-stat-label">Curators & Leads</span>
            <span className="sl-stat-subtext positive">Active writers</span>
          </div>
        </div>
      </div>

      {/* Department Filter Pills */}
      <div className="sl-categories-section">
        <span className="sl-categories-title">Filter by team space</span>
        <div className="sl-categories-row">
          {['All', 'Engineering', 'HR', 'Product', 'Finance', 'Legal', 'Support'].map((tag, i) => (
            <div
              key={i}
              className={`sl-category-chip ${selectedTag === tag ? 'active' : ''}`}
              onClick={() => setSelectedTag(tag)}
            >
              <span>{tag === 'All' ? 'All Spaces' : tag}</span>
              <span className="sl-cat-dot"></span>
            </div>
          ))}
        </div>
      </div>

      {/* Department Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 16 }}>
        {filteredDepts.map((dept) => (
          <div
            key={dept.id}
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 14,
              padding: '18px 20px',
              display: 'flex',
              flexDirection: 'column',
              gap: 14,
              boxShadow: '0 4px 20px -2px rgba(0,0,0,0.7)',
              transition: 'all 0.2s'
            }}
          >
            {/* Dept Card Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <span style={{ fontSize: 16, fontWeight: 700, color: '#fff' }}>{dept.name}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, fontSize: 12, color: '#94a3b8' }}>
                  <span>{dept.docCount}</span>
                  <span>•</span>
                  <span>{dept.storage}</span>
                  <span>•</span>
                  <span style={{ color: '#10b981', fontWeight: 600 }}>{dept.coverage} coverage</span>
                </div>
              </div>

              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  padding: '3px 9px',
                  borderRadius: 9999,
                  background: 'rgba(37, 99, 235, 0.15)',
                  color: '#3b82f6',
                  border: '1px solid rgba(37, 99, 235, 0.3)'
                }}
              >
                {dept.tag}
              </span>
            </div>

            {/* Pinned Artifacts */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                Key Pinned Artifacts
              </span>

              {dept.pinnedDocs.map((doc, idx) => (
                <div
                  key={idx}
                  onClick={() => setActivePreviewDoc({ ...doc, dept: dept.name })}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 10px',
                    background: 'var(--bg-app)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 8,
                    cursor: 'pointer',
                    transition: 'all 0.15s'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.borderColor = '#2563eb'}
                  onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--border-subtle)'}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, overflow: 'hidden' }}>
                    <FileText size={14} style={{ color: '#3b82f6', flexShrink: 0 }} />
                    <span style={{ fontSize: 12.5, fontWeight: 500, color: '#e2e8f0', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                      {doc.name}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: '#64748b', flexShrink: 0 }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                      <Eye size={12} /> {doc.views}
                    </span>
                    <ExternalLink size={12} />
                  </div>
                </div>
              ))}
            </div>

            {/* Card Footer */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 10, borderTop: '1px solid var(--border-subtle)', marginTop: 'auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <img
                  src={AVATARS[dept.lead] || AVATARS['Olivia Rhye']}
                  alt={dept.lead}
                  style={{ width: 22, height: 22, borderRadius: '50%' }}
                />
                <span style={{ fontSize: 12, color: '#94a3b8' }}>Lead: {dept.lead}</span>
              </div>

              <button
                style={{
                  background: '#2563eb',
                  color: '#fff',
                  fontSize: 12,
                  fontWeight: 600,
                  padding: '6px 12px',
                  borderRadius: 6,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  transition: 'background 0.2s'
                }}
                onClick={() => alert(`Opening ${dept.name} knowledge repository`)}
              >
                <span>Browse Space</span>
                <ExternalLink size={12} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Doc Preview Modal */}
      {activePreviewDoc && (
        <div className="modal-overlay" onClick={() => setActivePreviewDoc(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <FileText size={18} style={{ color: '#3b82f6' }} />
                <span className="modal-title">{activePreviewDoc.name}</span>
              </div>
              <button onClick={() => setActivePreviewDoc(null)} style={{ color: '#94a3b8' }}>
                <X size={20} />
              </button>
            </div>

            <div style={{ fontSize: 13, color: '#94a3b8', display: 'flex', gap: 14 }}>
              <span>Space: <strong style={{ color: '#fff' }}>{activePreviewDoc.dept}</strong></span>
              <span>Platform: <strong style={{ color: '#fff' }}>{activePreviewDoc.type}</strong></span>
              <span>Last audited: <strong style={{ color: '#fff' }}>{activePreviewDoc.updated}</strong></span>
            </div>

            <div style={{ background: 'var(--bg-app)', border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 16, fontSize: 13, lineHeight: 1.6, color: '#cbd5e1' }}>
              <p style={{ marginBottom: 10 }}>
                This document is indexed in the enterprise knowledge graph with high semantic weighting. Any updates made in the connected {activePreviewDoc.type} workspace are automatically re-indexed within 15 minutes.
              </p>
              <ul style={{ paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 4 }}>
                <li>Document classification: Enterprise Internal Only</li>
                <li>Embeddings status: Verified & Synced</li>
                <li>Recent unique accesses: {activePreviewDoc.views} team members</li>
              </ul>
            </div>

            <button
              className="add-source-primary-btn"
              style={{ alignSelf: 'flex-start' }}
              onClick={() => {
                alert(`Navigating to source repository for ${activePreviewDoc.name}`)
                setActivePreviewDoc(null)
              }}
            >
              <span>Open in {activePreviewDoc.type}</span>
              <ExternalLink size={14} />
            </button>
          </div>
        </div>
      )}
    </>
  )
}
