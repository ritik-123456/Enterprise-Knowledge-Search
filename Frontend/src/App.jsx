import { useState } from 'react'
import {
  Sparkles,
  ChevronDown,
  HelpCircle,
  Bell,
  MoreVertical,
  PanelLeftClose,
  PanelLeftOpen,
  PanelLeft,
  LogOut,
  User as UserIcon,
  Settings as SettingsIcon
} from 'lucide-react'
import './App.css'
import { AVATARS } from './components/BrandIcons'
import AskAI from './pages/AskAI'
import Settings from './pages/Settings'
import { useAuth } from './context/AuthContext'
import LoginModal from './components/LoginModal'

const GoogleIcon = () => (
  <svg className="google-icon-svg" viewBox="0 0 24 24">
    <path
      fill="#4285F4"
      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
    />
    <path
      fill="#34A853"
      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
    />
    <path
      fill="#FBBC05"
      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
    />
    <path
      fill="#EA4335"
      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
    />
  </svg>
)

const SUBMENU_METADATA = {
  'Ask AI': {
    title: 'Ask AI',
    subtitle: 'Get accurate answers from your company knowledge.'
  },
  'Settings': {
    title: 'Settings',
    subtitle: 'Workspace theme, appearance, and interface preferences.'
  }
}

export default function App() {
  const [activeTab, setActiveTab] = useState('Ask AI')
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [showNotifications, setShowNotifications] = useState(false)
  const [showUserDropdown, setShowUserDropdown] = useState(false)

  const { user, isAuthenticated, logout, setIsLoginModalOpen } = useAuth()

  const currentMeta = SUBMENU_METADATA[activeTab] || SUBMENU_METADATA['Ask AI']

  return (
    <div className="app-container">
      {/* ===================== SIDEBAR ===================== */}
      <aside className={`sidebar ${isSidebarOpen ? 'open' : 'collapsed'}`}>
        <div className="sidebar-top">
          {/* Brand Header with Close/Slide Button */}
          <div className="brand-header">
            <div className="brand-header-main">
              <div className="brand-icon-box">
                <Sparkles size={18} />
              </div>
              <div className="brand-title-wrap">
                <span className="brand-title-line">AI Internal</span>
                <span className="brand-title-line">Knowledge Search</span>
              </div>
            </div>

            <button
              className="sidebar-close-btn"
              onClick={() => setIsSidebarOpen(false)}
              title="Close sidebar"
            >
              <PanelLeftClose size={18} />
            </button>
          </div>

          {/* Navigation Items */}
          <nav className="sidebar-nav">
            <button
              className={`nav-item ${activeTab === 'Ask AI' ? 'active' : ''}`}
              onClick={() => setActiveTab('Ask AI')}
            >
              <Sparkles size={18} className="nav-icon" />
              <span>Ask AI</span>
            </button>

            <button
              className={`nav-item ${activeTab === 'Settings' ? 'active' : ''}`}
              onClick={() => setActiveTab('Settings')}
            >
              <SettingsIcon size={18} className="nav-icon" />
              <span>Settings</span>
            </button>
          </nav>
        </div>

        {/* Sidebar Footer */}
        <div className="sidebar-bottom">
          <div className="pro-plan-card">
            <div className="pro-header">
              <Sparkles size={16} className="pro-icon" />
              <span>Pro Plan</span>
            </div>
            <div className="pro-usage-row">
              <span>Usage this month</span>
              <span className="pro-percentage">78%</span>
            </div>
            <div className="progress-track">
              <div className="progress-bar-fill" style={{ width: '78%' }}></div>
            </div>
            <span className="pro-reset-text">Resets in 12 days</span>
          </div>

          {isAuthenticated && user ? (
            <div className="user-profile-menu-container">
              <div
                className="user-profile-card"
                onClick={() => setShowUserDropdown(!showUserDropdown)}
                style={{ cursor: 'pointer' }}
                title="Account Settings"
              >
                <div className="user-profile-left">
                  <img
                    src={user.picture || AVATARS['Olivia Rhye']}
                    alt={user.name}
                    className="user-avatar-img"
                    referrerPolicy="no-referrer"
                    onError={(e) => { e.target.src = AVATARS['Olivia Rhye'] }}
                  />
                  <div className="user-name-box">
                    <span className="user-display-name">{user.name}</span>
                    <span className="user-email-text">{user.email}</span>
                  </div>
                </div>
                <MoreVertical size={16} style={{ color: 'var(--text-muted)' }} />
              </div>

              {showUserDropdown && (
                <div className="user-profile-dropdown">
                  <div className="user-dropdown-header">
                    <div className="user-dropdown-name">{user.name}</div>
                    <div className="user-dropdown-email">{user.email}</div>
                    <span className="user-dropdown-role-tag">{user.role || 'Member'}</span>
                  </div>
                  <button
                    className="user-dropdown-item logout"
                    onClick={() => {
                      setShowUserDropdown(false)
                      logout()
                    }}
                  >
                    <LogOut size={14} />
                    <span>Sign Out</span>
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="sidebar-signin-banner">
              <span className="sidebar-signin-text">Sign in with Google to sync audit history & access controls</span>
              <button
                className="sidebar-signin-btn"
                onClick={() => setIsLoginModalOpen(true)}
              >
                <GoogleIcon />
                <span>Sign in with Google</span>
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* ===================== MAIN CONTENT WRAPPER ===================== */}
      <main className="main-wrapper">
        {/* Top Header with ChatGPT-style top Logo & Slide Button */}
        <header className="top-header">
          <div className="top-header-left">
            {!isSidebarOpen && (
              <button
                className="sidebar-toggle-btn"
                onClick={() => setIsSidebarOpen(true)}
                title="Open sidebar"
              >
                <PanelLeftOpen size={18} />
              </button>
            )}

            {/* Logo On Top like ChatGPT */}
            <div
              className="top-logo-badge"
              title="AI Internal Knowledge Search"
            >
              <div className="top-logo-icon">
                <Sparkles size={15} />
              </div>
              <span className="top-logo-title">AI Internal Knowledge Search</span>
            </div>

            <div className="top-header-breadcrumb">
              <span className="breadcrumb-divider">/</span>
              <span className="breadcrumb-current-tab">{currentMeta.title}</span>
            </div>
          </div>

          <div className="header-right-actions">
            <button className="icon-button" title="Help & Documentation">
              <HelpCircle size={18} />
            </button>

            <button
              className="icon-button"
              title="Notifications"
              onClick={() => setShowNotifications(!showNotifications)}
              style={{ position: 'relative' }}
            >
              <Bell size={18} />
              <span className="badge-counter">3</span>

              {showNotifications && (
                <div
                  style={{
                    position: 'absolute',
                    top: '110%',
                    right: 0,
                    width: '280px',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '12px',
                    padding: '12px',
                    zIndex: 60,
                    boxShadow: '0 12px 30px rgba(0,0,0,0.8)',
                    textAlign: 'left'
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: '13px', color: '#fff', marginBottom: '8px' }}>Recent Activity</div>
                  <div style={{ fontSize: '12px', color: '#cbd5e1', padding: '6px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                    #company-policy synced (1,245 messages)
                  </div>
                  <div style={{ fontSize: '12px', color: '#cbd5e1', padding: '6px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                    Rate limit alert on #random Slack channel
                  </div>
                  <div style={{ fontSize: '12px', color: '#cbd5e1', padding: '6px 0' }}>
                    Q4 Planning sync in progress
                  </div>
                </div>
              )}
            </button>

            {isAuthenticated && user ? (
              <div
                className="user-header-pill"
                onClick={() => setShowUserDropdown(!showUserDropdown)}
                style={{ cursor: 'pointer' }}
                title="Account Menu"
              >
                <img
                  src={user.picture || AVATARS['Olivia Rhye']}
                  alt={user.name}
                  className="pill-user-avatar"
                  referrerPolicy="no-referrer"
                  onError={(e) => { e.target.src = AVATARS['Olivia Rhye'] }}
                />
                <div className="pill-user-info">
                  <span className="pill-user-name">{user.name}</span>
                  <span className="pill-user-dept">{user.department || 'Platform Team'}</span>
                </div>
              </div>
            ) : (
              <button
                className="header-signin-btn"
                onClick={() => setIsLoginModalOpen(true)}
              >
                <GoogleIcon />
                <span>Sign in with Google</span>
              </button>
            )}
          </div>
        </header>

        {/* Main Content View */}
        {activeTab === 'Ask AI' && <AskAI />}
        {activeTab === 'Settings' && <Settings />}

        {/* Google Authentication Dialog */}
        <LoginModal />
      </main>
    </div>
  )
}
