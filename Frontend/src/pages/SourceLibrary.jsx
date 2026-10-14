import { useState } from 'react'
import {
  Search,
  Plus,
  ChevronDown,
  Filter,
  Layers,
  CheckCircle2,
  AlertCircle,
  HardDrive,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  ExternalLink,
  X
} from 'lucide-react'
import { renderSourceTypeIcon, AVATARS } from '../components/BrandIcons'

const SOURCES_TABLE_DATA = [
  {
    id: 'slack-company-policy',
    name: '#company-policy',
    type: 'Slack',
    owner: 'Olivia Rhye',
    accessScope: 'ACME Corp',
    syncStatus: 'Healthy',
    lastSync: '2 min ago',
    indexedFiles: '1,245',
    hasActionAlert: false,
    details: {
      subtitle: 'Slack • Public channel',
      syncFrequency: 'Every 15 minutes',
      lastSyncDetail: '2 minutes ago',
      indexedDetail: '1,245 messages',
      storageUsed: '1.2 GB',
      accessScopeText: 'ACME Corp',
      visibleTo: '👥 All employees (245)',
      topCollections: [
        { name: 'Policy Updates', count: '312 messages' },
        { name: 'Benefits & Perks', count: '198 messages' },
        { name: 'Remote Work', count: '154 messages' }
      ],
      recentActivity: [
        { type: 'success', title: 'Sync completed', desc: '2 minutes ago • 1,245 new items indexed' },
        { type: 'info', title: 'Sync started', desc: '17 minutes ago' },
        { type: 'success', title: 'Sync completed', desc: '32 minutes ago • 98 new items indexed' },
        { type: 'danger', title: 'Sync failed', desc: '6 hours ago • Rate limit exceeded' }
      ]
    }
  },
  {
    id: 'notion-employee-handbook',
    name: 'Employee Handbook',
    type: 'Notion',
    owner: 'Noah Levin',
    accessScope: 'ACME Corp',
    syncStatus: 'Healthy',
    lastSync: '15 min ago',
    indexedFiles: '362',
    hasActionAlert: false,
    details: {
      subtitle: 'Notion • Workspace Wiki',
      syncFrequency: 'Every 30 minutes',
      lastSyncDetail: '15 minutes ago',
      indexedDetail: '362 pages',
      storageUsed: '450 MB',
      accessScopeText: 'ACME Corp',
      visibleTo: '👥 All employees (245)',
      topCollections: [
        { name: 'HR Guidelines', count: '124 pages' },
        { name: 'Code of Conduct', count: '88 pages' },
        { name: 'Engineering Principles', count: '72 pages' }
      ],
      recentActivity: [
        { type: 'success', title: 'Sync completed', desc: '15 minutes ago • 12 updated pages' },
        { type: 'success', title: 'Sync completed', desc: '45 minutes ago • 4 new pages' }
      ]
    }
  },
  {
    id: 'drive-workplace-guidelines',
    name: 'Workplace Guidelines',
    type: 'Google Drive',
    owner: 'Olivia Rhye',
    accessScope: 'ACME Corp',
    syncStatus: 'Healthy',
    lastSync: '1 hr ago',
    indexedFiles: '1,104',
    hasActionAlert: false,
    details: {
      subtitle: 'Google Drive • Shared Drive',
      syncFrequency: 'Hourly',
      lastSyncDetail: '1 hour ago',
      indexedDetail: '1,104 files',
      storageUsed: '3.4 GB',
      accessScopeText: 'ACME Corp',
      visibleTo: '👥 All employees (245)',
      topCollections: [
        { name: 'Workplace Protocols', count: '410 files' },
        { name: 'Facilities & Security', count: '320 files' },
        { name: 'Office Layouts', count: '180 files' }
      ],
      recentActivity: [
        { type: 'success', title: 'Sync completed', desc: '1 hour ago • 45 new files indexed' },
        { type: 'success', title: 'Sync completed', desc: '2 hours ago • Clean index pass' }
      ]
    }
  },
  {
    id: 'confluence-engineering-wiki',
    name: 'Engineering Wiki',
    type: 'Confluence',
    owner: 'Liam Chen',
    accessScope: 'ACME Corp',
    syncStatus: 'Healthy',
    lastSync: '2 hr ago',
    indexedFiles: '2,317',
    hasActionAlert: false,
    details: {
      subtitle: 'Confluence • Space: ENG',
      syncFrequency: 'Every 2 hours',
      lastSyncDetail: '2 hours ago',
      indexedDetail: '2,317 docs',
      storageUsed: '5.8 GB',
      accessScopeText: 'ACME Corp',
      visibleTo: '👥 Engineering & Product (85)',
      topCollections: [
        { name: 'System Architecture', count: '640 pages' },
        { name: 'API Specifications', count: '420 pages' },
        { name: 'Incident Post-mortems', count: '310 pages' }
      ],
      recentActivity: [
        { type: 'success', title: 'Sync completed', desc: '2 hours ago • 22 docs updated' }
      ]
    }
  },
  {
    id: 'sharepoint-hr-policies',
    name: 'HR Policies',
    type: 'SharePoint',
    owner: 'Emma Davis',
    accessScope: 'HR Department',
    syncStatus: 'Healthy',
    lastSync: '3 hr ago',
    indexedFiles: '864',
    hasActionAlert: false,
    details: {
      subtitle: 'SharePoint • Document Library',
      syncFrequency: 'Every 4 hours',
      lastSyncDetail: '3 hours ago',
      indexedDetail: '864 files',
      storageUsed: '2.1 GB',
      accessScopeText: 'HR Department',
      visibleTo: '👥 HR Department (18)',
      topCollections: [
        { name: 'Compensation Bands', count: '210 files' },
        { name: 'Benefits Summaries', count: '180 files' },
        { name: 'Offer Letter Templates', count: '94 files' }
      ],
      recentActivity: [
        { type: 'success', title: 'Sync completed', desc: '3 hours ago • 8 files synced' }
      ]
    }
  },
  {
    id: 'slack-random',
    name: '#random',
    type: 'Slack',
    owner: 'Noah Levin',
    accessScope: 'Engineering',
    syncStatus: 'Failed',
    lastSync: '6 hr ago',
    indexedFiles: '—',
    hasActionAlert: true,
    details: {
      subtitle: 'Slack • Public channel',
      syncFrequency: 'Every 15 minutes',
      lastSyncDetail: '6 hours ago (Failed)',
      indexedDetail: 'Sync suspended',
      storageUsed: '0 GB',
      accessScopeText: 'Engineering',
      visibleTo: '👥 Engineering (62)',
      topCollections: [
        { name: 'Off-topic discussions', count: '0 messages' }
      ],
      recentActivity: [
        { type: 'danger', title: 'Sync failed', desc: '6 hours ago • Rate limit exceeded (HTTP 429)' },
        { type: 'info', title: 'Automatic retry queued', desc: 'Waiting for token quota reset' }
      ]
    }
  },
  {
    id: 'drive-q4-planning',
    name: 'Q4 Planning',
    type: 'Google Drive',
    owner: 'Olivia Rhye',
    accessScope: 'Finance',
    syncStatus: 'Syncing',
    lastSync: 'Syncing...',
    indexedFiles: '1,027',
    hasActionAlert: false,
    details: {
      subtitle: 'Google Drive • Shared Folder',
      syncFrequency: 'Realtime Webhook',
      lastSyncDetail: 'Currently in progress...',
      indexedDetail: '1,027 files',
      storageUsed: '1.9 GB',
      accessScopeText: 'Finance',
      visibleTo: '👥 Finance & Execs (24)',
      topCollections: [
        { name: 'Q4 Forecast Spreadsheets', count: '340 files' },
        { name: 'Department Budgets', count: '290 files' }
      ],
      recentActivity: [
        { type: 'info', title: 'Sync started', desc: 'Just now • Indexing 1,027 items' }
      ]
    }
  },
  {
    id: 'pdf-onboarding-docs',
    name: 'Onboarding Docs',
    type: 'PDF Documents',
    owner: 'Emma Davis',
    accessScope: 'ACME Corp',
    syncStatus: 'Healthy',
    lastSync: '1 day ago',
    indexedFiles: '215',
    hasActionAlert: false,
    details: {
      subtitle: 'PDF Documents • S3 Storage',
      syncFrequency: 'Daily',
      lastSyncDetail: '1 day ago',
      indexedDetail: '215 documents',
      storageUsed: '680 MB',
      accessScopeText: 'ACME Corp',
      visibleTo: '👥 All employees (245)',
      topCollections: [
        { name: 'New Hire Welcome Packets', count: '110 docs' },
        { name: 'Benefits Enrollment Guides', count: '65 docs' }
      ],
      recentActivity: [
        { type: 'success', title: 'Sync completed', desc: '1 day ago • 215 documents verified' }
      ]
    }
  }
]

export default function SourceLibrary() {
  const [selectedSource, setSelectedSource] = useState(SOURCES_TABLE_DATA[0])
  const [drawerOpen, setDrawerOpen] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('All')
  const [typeFilter, setTypeFilter] = useState('All types')
  const [statusFilter, setStatusFilter] = useState('All status')
  const [ownerFilter, setOwnerFilter] = useState('All owners')
  const [accessFilter, setAccessFilter] = useState('All access')
  const [showAddSourceModal, setShowAddSourceModal] = useState(false)

  const filteredSources = SOURCES_TABLE_DATA.filter((s) => {
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      const matchesName = s.name.toLowerCase().includes(q)
      const matchesOwner = s.owner.toLowerCase().includes(q)
      const matchesType = s.type.toLowerCase().includes(q)
      if (!matchesName && !matchesOwner && !matchesType) return false
    }
    if (selectedCategory !== 'All' && s.type !== selectedCategory) return false
    if (typeFilter !== 'All types' && s.type !== typeFilter) return false
    if (statusFilter !== 'All status' && s.syncStatus !== statusFilter) return false
    if (ownerFilter !== 'All owners' && s.owner !== ownerFilter) return false
    if (accessFilter !== 'All access' && s.accessScope !== accessFilter) return false
    return true
  })

  return (
    <>
      {/* Search and Add Source Row */}
      <div className="sl-search-action-row">
        <div className="sl-search-box">
          <Search size={16} style={{ color: '#64748b' }} />
          <input
            type="text"
            className="sl-search-input"
            placeholder="Search sources by name or owner..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <button
          className="add-source-primary-btn"
          onClick={() => setShowAddSourceModal(true)}
        >
          <Plus size={16} />
          <span>Add Source</span>
        </button>
      </div>

      {/* Dropdown Filters Row */}
      <div className="sl-filters-row">
        <div className="sl-dropdown-group">
          <div
            className="sl-dropdown-pill"
            onClick={() => {
              const types = ['All types', 'Slack', 'Notion', 'Google Drive', 'Confluence', 'SharePoint', 'PDF Documents']
              const next = types[(types.indexOf(typeFilter) + 1) % types.length]
              setTypeFilter(next)
            }}
          >
            <span>{typeFilter}</span>
            <ChevronDown size={14} style={{ color: '#64748b' }} />
          </div>

          <div
            className="sl-dropdown-pill"
            onClick={() => {
              const statuses = ['All status', 'Healthy', 'Failed', 'Syncing']
              const next = statuses[(statuses.indexOf(statusFilter) + 1) % statuses.length]
              setStatusFilter(next)
            }}
          >
            <span>{statusFilter}</span>
            <ChevronDown size={14} style={{ color: '#64748b' }} />
          </div>

          <div
            className="sl-dropdown-pill"
            onClick={() => {
              const owners = ['All owners', 'Olivia Rhye', 'Noah Levin', 'Liam Chen', 'Emma Davis']
              const next = owners[(owners.indexOf(ownerFilter) + 1) % owners.length]
              setOwnerFilter(next)
            }}
          >
            <span>{ownerFilter}</span>
            <ChevronDown size={14} style={{ color: '#64748b' }} />
          </div>

          <div
            className="sl-dropdown-pill"
            onClick={() => {
              const scopes = ['All access', 'ACME Corp', 'HR Department', 'Engineering', 'Finance']
              const next = scopes[(scopes.indexOf(accessFilter) + 1) % scopes.length]
              setAccessFilter(next)
            }}
          >
            <span>{accessFilter}</span>
            <ChevronDown size={14} style={{ color: '#64748b' }} />
          </div>
        </div>

        <button
          className="sl-filters-btn"
          onClick={() => {
            setTypeFilter('All types')
            setStatusFilter('All status')
            setOwnerFilter('All owners')
            setAccessFilter('All access')
            setSelectedCategory('All')
            setSearchQuery('')
          }}
        >
          <Filter size={14} />
          <span>Filters</span>
        </button>
      </div>

      {/* 4 Stats Cards in Row */}
      <div className="sl-stats-grid">
        <div className="sl-stat-card">
          <div className="sl-stat-icon-box blue">
            <Layers size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">32</span>
            <span className="sl-stat-label">Total sources</span>
            <span className="sl-stat-subtext positive">
              <ArrowUp size={12} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 2 }} />
              4 this month
            </span>
          </div>
        </div>

        <div className="sl-stat-card">
          <div className="sl-stat-icon-box green">
            <CheckCircle2 size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">28</span>
            <span className="sl-stat-label">Healthy syncs</span>
            <span className="sl-stat-subtext">87.5% of total</span>
          </div>
        </div>

        <div className="sl-stat-card">
          <div className="sl-stat-icon-box red">
            <AlertCircle size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">2</span>
            <span className="sl-stat-label">Failed syncs</span>
            <span className="sl-stat-subtext danger">Needs attention</span>
          </div>
        </div>

        <div className="sl-stat-card">
          <div className="sl-stat-icon-box purple">
            <HardDrive size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">512 GB</span>
            <span className="sl-stat-label">Storage indexed</span>
            <span className="sl-stat-subtext positive">
              <ArrowUp size={12} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 2 }} />
              18 GB this month
            </span>
          </div>
        </div>
      </div>

      {/* Source Categories Row */}
      <div className="sl-categories-section">
        <span className="sl-categories-title">Source categories</span>
        <div className="sl-categories-row">
          {[
            { name: 'Slack', count: '8 sources' },
            { name: 'Notion', count: '6 sources' },
            { name: 'Google Drive', count: '7 sources' },
            { name: 'Confluence', count: '4 sources' },
            { name: 'SharePoint', count: '3 sources' },
            { name: 'PDF Documents', count: '2 sources' },
            { name: 'Internal Docs', count: '2 sources' }
          ].map((cat, i) => (
            <div
              key={i}
              className={`sl-category-chip ${selectedCategory === cat.name ? 'active' : ''}`}
              onClick={() => setSelectedCategory(selectedCategory === cat.name ? 'All' : cat.name)}
            >
              {renderSourceTypeIcon(cat.name, 16)}
              <span>{cat.name}</span>
              <span className="sl-cat-count">{cat.count}</span>
              <span className="sl-cat-dot"></span>
            </div>
          ))}
        </div>
      </div>

      {/* Main Split: All sources Table + Right Detail Drawer */}
      <div className={`sl-main-split ${!drawerOpen ? 'drawer-closed' : ''}`}>
        {/* Left Panel: Table */}
        <div className="sl-table-card">
          <span className="sl-table-header-title">All sources ({filteredSources.length})</span>

          <div className="sl-table-container">
            <table className="sl-table">
              <thead>
                <tr>
                  <th>Source name</th>
                  <th>Type</th>
                  <th>Owner</th>
                  <th>Access scope</th>
                  <th>Sync status</th>
                  <th>Last sync</th>
                  <th>Indexed files</th>
                  <th style={{ textAlign: 'center' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredSources.map((row) => {
                  const isSelected = selectedSource?.id === row.id
                  return (
                    <tr
                      key={row.id}
                      className={isSelected ? 'selected-row' : ''}
                      onClick={() => {
                        setSelectedSource(row)
                        setDrawerOpen(true)
                      }}
                    >
                      <td>
                        <div className="table-source-name-cell">
                          {renderSourceTypeIcon(row.type, 16)}
                          <span>{row.name}</span>
                        </div>
                      </td>
                      <td>{row.type}</td>
                      <td>
                        <div className="table-owner-cell">
                          <img
                            src={AVATARS[row.owner] || AVATARS['Olivia Rhye']}
                            alt={row.owner}
                            className="table-owner-avatar"
                          />
                          <span>{row.owner}</span>
                        </div>
                      </td>
                      <td>{row.accessScope}</td>
                      <td>
                        {row.syncStatus === 'Healthy' && (
                          <span className="status-badge-healthy">Healthy</span>
                        )}
                        {row.syncStatus === 'Failed' && (
                          <span className="status-badge-failed">Failed</span>
                        )}
                        {row.syncStatus === 'Syncing' && (
                          <span className="status-badge-syncing">
                            Syncing <RefreshCw size={11} className="animate-spin" style={{ display: 'inline', marginLeft: 2 }} />
                          </span>
                        )}
                      </td>
                      <td>{row.lastSync}</td>
                      <td>{row.indexedFiles}</td>
                      <td style={{ textAlign: 'center' }}>
                        {row.hasActionAlert ? (
                          <span className="action-alert-badge" title="Sync requires attention">!</span>
                        ) : (
                          <button style={{ color: 'var(--text-muted)' }}>•••</button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Table Footer / Pagination */}
          <div className="sl-pagination-bar">
            <span>Showing 1 to {filteredSources.length} of 32 sources</span>

            <div className="sl-page-numbers-group">
              <button className="sl-page-btn">
                <ChevronLeft size={14} />
              </button>
              <button className="sl-page-btn active">1</button>
              <button className="sl-page-btn">2</button>
              <button className="sl-page-btn">3</button>
              <button className="sl-page-btn">4</button>
              <button className="sl-page-btn">
                <ChevronRight size={14} />
              </button>
            </div>

            <span style={{ cursor: 'pointer' }}>8 / page ▾</span>
          </div>
        </div>

        {/* Right Panel: Detail Drawer */}
        {drawerOpen && selectedSource && (
          <div className="sl-detail-drawer">
            <div className="drawer-header">
              <div className="drawer-header-left">
                <div className="drawer-brand-icon">
                  {renderSourceTypeIcon(selectedSource.type, 22)}
                </div>
                <div className="drawer-title-group">
                  <div className="drawer-title-link">
                    <span>{selectedSource.name}</span>
                    <ExternalLink size={13} style={{ color: '#3b82f6', cursor: 'pointer' }} />
                  </div>
                  <span className="drawer-subtitle">{selectedSource.details.subtitle}</span>
                </div>
              </div>

              <button
                className="drawer-close-btn"
                onClick={() => setDrawerOpen(false)}
                title="Close drawer"
              >
                <X size={16} />
              </button>
            </div>

            <div className="drawer-section">
              <div className="drawer-section-header">
                <span className="drawer-section-title">Overview</span>
                <span className="drawer-status-pill">
                  {selectedSource.syncStatus}
                </span>
              </div>

              <div className="drawer-meta-list">
                <div className="drawer-meta-row">
                  <span className="drawer-meta-key">Sync frequency</span>
                  <span className="drawer-meta-val">{selectedSource.details.syncFrequency}</span>
                </div>
                <div className="drawer-meta-row">
                  <span className="drawer-meta-key">Last sync</span>
                  <span className="drawer-meta-val">{selectedSource.details.lastSyncDetail}</span>
                </div>
                <div className="drawer-meta-row">
                  <span className="drawer-meta-key">Indexed files</span>
                  <span className="drawer-meta-val">{selectedSource.details.indexedDetail}</span>
                </div>
                <div className="drawer-meta-row">
                  <span className="drawer-meta-key">Storage used</span>
                  <span className="drawer-meta-val">{selectedSource.details.storageUsed}</span>
                </div>
                <div className="drawer-meta-row">
                  <span className="drawer-meta-key">Connected by</span>
                  <span className="drawer-meta-val">
                    <img
                      src={AVATARS[selectedSource.owner] || AVATARS['Olivia Rhye']}
                      alt={selectedSource.owner}
                      style={{ width: 18, height: 18, borderRadius: '50%' }}
                    />
                    {selectedSource.owner}
                  </span>
                </div>
              </div>

              <button className="drawer-action-btn-outline">
                <span>View source</span>
                <ExternalLink size={12} />
              </button>
            </div>

            <div className="drawer-section">
              <span className="drawer-section-title">Permissions & scope</span>
              <div className="drawer-meta-list">
                <div className="drawer-meta-row">
                  <span className="drawer-meta-key">Access scope</span>
                  <span className="drawer-meta-val">{selectedSource.details.accessScopeText}</span>
                </div>
                <div className="drawer-meta-row">
                  <span className="drawer-meta-key">Visible to</span>
                  <span className="drawer-meta-val">{selectedSource.details.visibleTo}</span>
                </div>
              </div>
            </div>

            <div className="drawer-section">
              <div className="drawer-section-header">
                <span className="drawer-section-title">Top collections</span>
                <button style={{ color: '#3b82f6', fontSize: '11px', fontWeight: 500 }}>View all</button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {selectedSource.details.topCollections.map((col, idx) => (
                  <div key={idx} className="drawer-collection-item">
                    <div className="drawer-coll-left">
                      <span className="drawer-coll-num">{idx + 1}</span>
                      <span className="drawer-coll-name">{col.name}</span>
                    </div>
                    <span className="drawer-coll-meta">{col.count}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="drawer-section">
              <span className="drawer-section-title">Recent activity</span>

              <div className="drawer-activity-timeline">
                {selectedSource.details.recentActivity.map((act, idx) => (
                  <div key={idx} className="activity-node">
                    <span className={`activity-node-dot ${act.type === 'info' ? 'blue' : act.type === 'danger' ? 'red' : ''}`}></span>
                    <span className="activity-node-title">{act.title}</span>
                    <span className="activity-node-desc">{act.desc}</span>
                  </div>
                ))}
              </div>

              <button style={{ color: '#3b82f6', fontSize: '12px', fontWeight: 500, alignSelf: 'center', marginTop: 4 }}>
                View all activity ↗
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modal: Add Source */}
      {showAddSourceModal && (
        <div className="modal-overlay" onClick={() => setShowAddSourceModal(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">Connect New Knowledge Source</div>
              <button onClick={() => setShowAddSourceModal(false)} style={{ color: '#94a3b8' }}>
                <X size={20} />
              </button>
            </div>
            <p style={{ fontSize: '13px', color: '#94a3b8' }}>
              Select an enterprise platform to index channels, workspaces, or cloud folders.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px' }}>
              {[
                { name: 'Slack Channel', type: 'Slack', desc: 'Sync public or private channels' },
                { name: 'Notion Workspace', type: 'Notion', desc: 'Sync team spaces & databases' },
                { name: 'Google Drive', type: 'Google Drive', desc: 'Sync shared drives & folders' },
                { name: 'Confluence Space', type: 'Confluence', desc: 'Sync architecture wikis' },
                { name: 'SharePoint Library', type: 'SharePoint', desc: 'Sync Microsoft 365 sites' },
                { name: 'PDF Documents / S3', type: 'PDF Documents', desc: 'Sync cloud document buckets' }
              ].map((item, idx) => (
                <div
                  key={idx}
                  style={{
                    background: 'var(--bg-app)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '10px',
                    padding: '12px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px',
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                  }}
                  onClick={() => {
                    alert(`Initiating OAuth connection flow for ${item.name}...`)
                    setShowAddSourceModal(false)
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {renderSourceTypeIcon(item.type, 18)}
                    <span style={{ fontSize: '13px', fontWeight: 600, color: '#fff' }}>{item.name}</span>
                  </div>
                  <span style={{ fontSize: '11px', color: '#64748b' }}>{item.desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
