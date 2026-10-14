import { useState } from 'react'
import {
  ShieldCheck,
  ShieldAlert,
  Users,
  Lock,
  Plus,
  Check,
  X,
  Sliders,
  ChevronDown,
  Info
} from 'lucide-react'
import { AVATARS } from '../components/BrandIcons'

const ROLES = [
  {
    id: 'admin',
    name: 'Enterprise Admin',
    desc: 'Full read & indexing control across all enterprise connectors, audit trails, and member access.',
    membersCount: 4,
    members: ['Olivia Rhye', 'Liam Chen'],
    color: '#2563eb'
  },
  {
    id: 'eng',
    name: 'Engineering & DevOps',
    desc: 'Access to technical documentation, code repositories, architecture wikis, and cloud incident runbooks.',
    membersCount: 58,
    members: ['Liam Chen', 'Noah Levin'],
    color: '#3b82f6'
  },
  {
    id: 'hr',
    name: 'People Operations & HR',
    desc: 'Access to employee records, compensation matrices, benefit plans, and confidential hiring documents.',
    membersCount: 14,
    members: ['Emma Davis'],
    color: '#10b981'
  },
  {
    id: 'all',
    name: 'All Employees (Standard)',
    desc: 'Access to company-wide handbooks, office guidelines, travel policies, and public Slack channels.',
    membersCount: 245,
    members: ['Olivia Rhye', 'Noah Levin', 'Emma Davis'],
    color: '#64748b'
  }
]

const PERMISSION_MATRIX = [
  {
    source: '#company-policy (Slack)',
    type: 'Slack',
    roles: { admin: true, eng: true, hr: true, all: true }
  },
  {
    source: 'Employee Handbook (Notion)',
    type: 'Notion',
    roles: { admin: true, eng: true, hr: true, all: true }
  },
  {
    source: 'Engineering Architecture (Confluence)',
    type: 'Confluence',
    roles: { admin: true, eng: true, hr: false, all: false }
  },
  {
    source: 'Compensation & Salary Bands (SharePoint)',
    type: 'SharePoint',
    roles: { admin: true, eng: false, hr: true, all: false }
  },
  {
    source: 'Q4 Financial Models & Projections (Drive)',
    type: 'Google Drive',
    roles: { admin: true, eng: false, hr: false, all: false }
  },
  {
    source: 'Customer Onboarding Guides (Wikis)',
    type: 'Wikis',
    roles: { admin: true, eng: true, hr: true, all: true }
  }
]

export default function AccessControl() {
  const [matrix, setMatrix] = useState(PERMISSION_MATRIX)
  const [selectedRoleTab, setSelectedRoleTab] = useState('admin')

  const togglePermission = (sourceName, roleKey) => {
    setMatrix(list =>
      list.map(item => {
        if (item.source === sourceName) {
          return {
            ...item,
            roles: { ...item.roles, [roleKey]: !item.roles[roleKey] }
          }
        }
        return item
      })
    )
  }

  return (
    <>
      {/* Top Action Row */}
      <div className="sl-search-action-row">
        <div>
          <span style={{ fontSize: 13, color: '#94a3b8' }}>
            Configure Role-Based Access Control (RBAC), data fences, and document privacy tiers.
          </span>
        </div>

        <button className="add-source-primary-btn" onClick={() => alert('New role modal')}>
          <Plus size={16} />
          <span>Create Custom Role</span>
        </button>
      </div>

      {/* 4 Stats Cards */}
      <div className="sl-stats-grid">
        <div className="sl-stat-card">
          <div className="sl-stat-icon-box blue">
            <ShieldCheck size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">4</span>
            <span className="sl-stat-label">Active Security Roles</span>
            <span className="sl-stat-subtext positive">Enforced via SSO</span>
          </div>
        </div>

        <div className="sl-stat-card">
          <div className="sl-stat-icon-box green">
            <Lock size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">32</span>
            <span className="sl-stat-label">Guarded Sources</span>
            <span className="sl-stat-subtext positive">0 Leaks detected</span>
          </div>
        </div>

        <div className="sl-stat-card">
          <div className="sl-stat-icon-box blue">
            <Sliders size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">8</span>
            <span className="sl-stat-label">Data Privacy Fences</span>
            <span className="sl-stat-subtext">PII & Financial</span>
          </div>
        </div>

        <div className="sl-stat-card">
          <div className="sl-stat-icon-box green">
            <Check size={20} />
          </div>
          <div className="sl-stat-info">
            <span className="sl-stat-value">100%</span>
            <span className="sl-stat-label">SOC2 Compliance</span>
            <span className="sl-stat-subtext positive">Audit trail enabled</span>
          </div>
        </div>
      </div>

      {/* Role Cards Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 }}>
        {ROLES.map((role) => (
          <div
            key={role.id}
            style={{
              background: 'var(--bg-card)',
              border: selectedRoleTab === role.id ? '1px solid #2563eb' : '1px solid var(--border-subtle)',
              borderRadius: 12,
              padding: '16px 18px',
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
              boxShadow: '0 4px 20px -2px rgba(0,0,0,0.7)',
              cursor: 'pointer',
              transition: 'all 0.15s'
            }}
            onClick={() => setSelectedRoleTab(role.id)}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 15, fontWeight: 700, color: '#fff' }}>{role.name}</span>
              <span style={{ fontSize: 12, color: '#10b981', fontWeight: 600 }}>{role.membersCount} members</span>
            </div>

            <p style={{ fontSize: 12.5, color: '#94a3b8', lineHeight: 1.4 }}>{role.desc}</p>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 4, paddingTop: 10, borderTop: '1px solid var(--border-subtle)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: -6 }}>
                {role.members.map((m, i) => (
                  <img
                    key={i}
                    src={AVATARS[m] || AVATARS['Olivia Rhye']}
                    alt={m}
                    style={{ width: 22, height: 22, borderRadius: '50%', border: '2px solid var(--bg-card)', marginRight: -6 }}
                  />
                ))}
              </div>

              <span style={{ fontSize: 11, color: '#2563eb', fontWeight: 600 }}>
                {selectedRoleTab === role.id ? 'Viewing matrix' : 'Select role →'}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Permissions Matrix Table */}
      <div className="sl-table-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span className="sl-table-header-title">Document Privacy & Source Access Matrix</span>
            <p style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>
              Toggle checkboxes to grant or revoke document retrieval for each role tier.
            </p>
          </div>

          <button
            style={{
              background: '#10b981',
              color: '#fff',
              fontSize: 12,
              fontWeight: 600,
              padding: '6px 14px',
              borderRadius: 6
            }}
            onClick={() => alert('Access policies saved & propagated across vector indexes')}
          >
            Save Policy Changes
          </button>
        </div>

        <div className="sl-table-container">
          <table className="sl-table">
            <thead>
              <tr>
                <th>Knowledge Source</th>
                <th>Type</th>
                <th style={{ textAlign: 'center' }}>Enterprise Admin</th>
                <th style={{ textAlign: 'center' }}>Engineering</th>
                <th style={{ textAlign: 'center' }}>HR & People</th>
                <th style={{ textAlign: 'center' }}>All Employees</th>
              </tr>
            </thead>
            <tbody>
              {matrix.map((row, idx) => (
                <tr key={idx}>
                  <td style={{ fontWeight: 600, color: '#f8fafc' }}>{row.source}</td>
                  <td>
                    <span style={{ fontSize: 11.5, color: '#94a3b8' }}>{row.type}</span>
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <button
                      onClick={() => togglePermission(row.source, 'admin')}
                      style={{
                        width: 24,
                        height: 24,
                        borderRadius: 6,
                        background: row.roles.admin ? '#2563eb' : '#262626',
                        color: '#fff',
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center'
                      }}
                    >
                      {row.roles.admin ? <Check size={14} /> : <X size={14} style={{ color: '#64748b' }} />}
                    </button>
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <button
                      onClick={() => togglePermission(row.source, 'eng')}
                      style={{
                        width: 24,
                        height: 24,
                        borderRadius: 6,
                        background: row.roles.eng ? '#2563eb' : '#262626',
                        color: '#fff',
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center'
                      }}
                    >
                      {row.roles.eng ? <Check size={14} /> : <X size={14} style={{ color: '#64748b' }} />}
                    </button>
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <button
                      onClick={() => togglePermission(row.source, 'hr')}
                      style={{
                        width: 24,
                        height: 24,
                        borderRadius: 6,
                        background: row.roles.hr ? '#10b981' : '#262626',
                        color: '#fff',
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center'
                      }}
                    >
                      {row.roles.hr ? <Check size={14} /> : <X size={14} style={{ color: '#64748b' }} />}
                    </button>
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <button
                      onClick={() => togglePermission(row.source, 'all')}
                      style={{
                        width: 24,
                        height: 24,
                        borderRadius: 6,
                        background: row.roles.all ? '#2563eb' : '#262626',
                        color: '#fff',
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center'
                      }}
                    >
                      {row.roles.all ? <Check size={14} /> : <X size={14} style={{ color: '#64748b' }} />}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
