import { useState, useEffect, useRef } from 'react'
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
  Settings as SettingsIcon,
  SquarePen,
  Search,
  LayoutGrid,
  Clock,
  Compass,
  GraduationCap
} from 'lucide-react'
import './App.css'
import { AVATARS } from './components/BrandIcons'
import AskAI from './pages/AskAI'
import Settings from './pages/Settings'
import ChatHistory from './pages/ChatHistory'
import { useAuth } from './context/AuthContext'
import { useChat } from './context/ChatContext'
import LoginModal from './components/LoginModal'
import MarvoLogo from './components/MarvoLogo'

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

const GuestAvatarIcon = ({ size = 20, className = '' }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={{ display: 'block', flexShrink: 0 }}
  >
    <circle cx="12" cy="12" r="10" />
    <circle cx="12" cy="10" r="3.2" />
    <path d="M5.5 19.5c1.2-3 3.5-4.5 6.5-4.5s5.3 1.5 6.5 4.5" />
  </svg>
)

const SUBMENU_METADATA = {
  'Ask AI': {
    title: 'Ask AI',
    subtitle: 'Get accurate answers from your company knowledge.'
  },
  'Chats': {
    title: 'Chat Search & History',
    subtitle: 'Search and reopen previous conversations stored in Supabase.'
  },
  'Settings': {
    title: 'Settings',
    subtitle: 'Workspace theme, appearance, and interface preferences.'
  }
}

export default function App() {
  const [activeTab, setActiveTab] = useState('Ask AI')
  const [isSidebarExpanded, setIsSidebarExpanded] = useState(false)
  const [showNotifications, setShowNotifications] = useState(false)
  const [showUserDropdown, setShowUserDropdown] = useState(false)
  const [showHeaderDropdown, setShowHeaderDropdown] = useState(false)

  const sidebarUserDropdownRef = useRef(null)
  const headerUserDropdownRef = useRef(null)
  const notificationsRef = useRef(null)

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        sidebarUserDropdownRef.current &&
        !sidebarUserDropdownRef.current.contains(event.target)
      ) {
        setShowUserDropdown(false)
      }
      if (
        headerUserDropdownRef.current &&
        !headerUserDropdownRef.current.contains(event.target)
      ) {
        setShowHeaderDropdown(false)
      }
      if (
        notificationsRef.current &&
        !notificationsRef.current.contains(event.target)
      ) {
        setShowNotifications(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  const { user, isAuthenticated, logout, setIsLoginModalOpen } = useAuth()
  const { chats, activeChat, loadChat, startNewChat } = useChat()

  const currentMeta = SUBMENU_METADATA[activeTab] || SUBMENU_METADATA['Ask AI']

  return (
    <div className="app-container">
      {/* ===================== GEMINI-STYLE SIDEBAR ===================== */}
      <aside className={`gemini-sidebar ${isSidebarExpanded ? 'expanded' : ''}`}>
        {!isSidebarExpanded ? (
          /* ================= SHORT SIDEBAR RAIL (52px) ================= */
          <>
            <div className="gemini-sidebar-top">
              {/* Top Logo Button with Hover Swap to Open Sidebar Icon */}
              <button
                className="gemini-logo-toggle-btn"
                onClick={() => {
                  setShowUserDropdown(false)
                  setIsSidebarExpanded(true)
                }}
                title="Open sidebar"
                aria-label="Open sidebar"
              >
                <span className="logo-swap-default">
                  <MarvoLogo size={20} />
                </span>
                <span className="logo-swap-hover">
                  <PanelLeftOpen size={18} />
                </span>
              </button>

              {/* Action Icons Stack */}
              <div className="gemini-nav-stack">
                <button
                  className={`gemini-rail-btn ${activeTab === 'Ask AI' && !activeChat ? 'active' : ''}`}
                  onClick={() => {
                    startNewChat()
                    setActiveTab('Ask AI')
                  }}
                  title="New Chat / Ask AI"
                >
                  <SquarePen size={18} />
                </button>

                {/* Search to Learning & Guidance: Only shown when signed in */}
                {isAuthenticated && (
                  <>
                    <button
                      className={`gemini-rail-btn ${activeTab === 'Chats' ? 'active' : ''}`}
                      onClick={() => setActiveTab('Chats')}
                      title="Search Chats & Stored History"
                    >
                      <Search size={18} />
                    </button>

                    <button
                      className="gemini-rail-btn"
                      onClick={() => setActiveTab('Ask AI')}
                      title="Workspaces & Data"
                    >
                      <LayoutGrid size={18} />
                    </button>

                    <button
                      className="gemini-rail-btn"
                      onClick={() => setActiveTab('Ask AI')}
                      title="Explore"
                    >
                      <Compass size={18} />
                    </button>

                    <button
                      className="gemini-rail-btn"
                      onClick={() => setActiveTab('Ask AI')}
                      title="Recent Activity"
                    >
                      <Clock size={18} />
                    </button>

                    <button
                      className="gemini-rail-btn"
                      onClick={() => setActiveTab('Ask AI')}
                      title="Learning & Guidance"
                    >
                      <GraduationCap size={18} />
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Bottom: Settings above User Profile */}
            <div className="gemini-sidebar-bottom">
              <button
                className={`gemini-rail-btn ${activeTab === 'Settings' ? 'active' : ''}`}
                onClick={() => setActiveTab('Settings')}
                title="Settings"
              >
                <SettingsIcon size={18} />
              </button>

              {/* User Profile Avatar / Sign-In */}
              <div
                ref={sidebarUserDropdownRef}
                className="gemini-avatar-wrapper"
                onClick={() => {
                  if (isAuthenticated && user) {
                    setShowUserDropdown((prev) => !prev)
                  } else {
                    setIsLoginModalOpen(true)
                  }
                }}
                title={isAuthenticated && user ? user.name : "Sign In with Google"}
              >
                {isAuthenticated && user?.picture ? (
                  <img
                    src={user.picture}
                    alt={user.name || "User"}
                    className="gemini-avatar-img"
                    referrerPolicy="no-referrer"
                  />
                ) : isAuthenticated && user?.name ? (
                  <div className="gemini-avatar-circle">
                    {user.name[0].toUpperCase()}
                  </div>
                ) : (
                  <div className="gemini-guest-avatar-box">
                    <GuestAvatarIcon size={20} />
                  </div>
                )}

                {/* Profile Dropdown Menu */}
                {showUserDropdown && isAuthenticated && user && (
                  <div className="gemini-user-dropdown" onClick={(e) => e.stopPropagation()}>
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
            </div>
          </>
        ) : (
          /* ================= COMPLETE EXPANDED SIDEBAR (250px) ================= */
          <div className="gemini-expanded-container">
            {/* Expanded Header */}
            <div className="gemini-expanded-header">
              <div
                className="gemini-expanded-brand"
                onClick={() => {
                  setActiveTab('Ask AI')
                  setIsSidebarExpanded(false)
                }}
                title="MARVO AI"
              >
                <MarvoLogo size={20} />
                <span className="gemini-brand-text">MARVO</span>
                <span className="gemini-brand-badge">AI</span>
              </div>
              <button
                className="gemini-sidebar-close-btn"
                onClick={() => setIsSidebarExpanded(false)}
                title="Collapse sidebar"
                aria-label="Collapse sidebar"
              >
                <PanelLeftClose size={18} />
              </button>
            </div>

            {/* Expanded Navigation Links */}
            <div className="gemini-expanded-nav">
              <button
                className={`gemini-expanded-nav-item ${activeTab === 'Ask AI' && !activeChat ? 'active' : ''}`}
                onClick={() => {
                  startNewChat()
                  setActiveTab('Ask AI')
                  setIsSidebarExpanded(false)
                }}
              >
                <SquarePen size={17} className="expanded-nav-icon" />
                <span className="expanded-nav-label">New Chat</span>
              </button>

              {/* Search to Learning & Guidance: Only shown when signed in */}
              {isAuthenticated && (
                <>
                  <button
                    className={`gemini-expanded-nav-item ${activeTab === 'Chats' ? 'active' : ''}`}
                    onClick={() => {
                      setActiveTab('Chats')
                      setIsSidebarExpanded(false)
                    }}
                  >
                    <Search size={17} className="expanded-nav-icon" />
                    <span className="expanded-nav-label">Search Chats</span>
                  </button>

                  <button
                    className="gemini-expanded-nav-item"
                    onClick={() => {
                      setActiveTab('Ask AI')
                      setIsSidebarExpanded(false)
                    }}
                  >
                    <LayoutGrid size={17} className="expanded-nav-icon" />
                    <span className="expanded-nav-label">Workspaces & Data</span>
                  </button>

                  <button
                    className="gemini-expanded-nav-item"
                    onClick={() => {
                      setActiveTab('Ask AI')
                      setIsSidebarExpanded(false)
                    }}
                  >
                    <Compass size={17} className="expanded-nav-icon" />
                    <span className="expanded-nav-label">Explore</span>
                  </button>

                  <button
                    className="gemini-expanded-nav-item"
                    onClick={() => {
                      setActiveTab('Ask AI')
                      setIsSidebarExpanded(false)
                    }}
                  >
                    <Clock size={17} className="expanded-nav-icon" />
                    <span className="expanded-nav-label">Recent Activity</span>
                  </button>

                  <button
                    className="gemini-expanded-nav-item"
                    onClick={() => {
                      setActiveTab('Ask AI')
                      setIsSidebarExpanded(false)
                    }}
                  >
                    <GraduationCap size={17} className="expanded-nav-icon" />
                    <span className="expanded-nav-label">Guides & Docs</span>
                  </button>
                </>
              )}
            </div>

            {/* Recents Section in Expanded Sidebar: Only shown when signed in */}
            {isAuthenticated && (
              <div className="gemini-expanded-recents">
                <div className="gemini-recents-heading">Recent Conversations</div>
                <div className="gemini-recents-list">
                  {chats && chats.length > 0 ? (
                    chats.slice(0, 5).map((c) => (
                      <div
                        key={c.id}
                        className={`gemini-recent-item ${activeChat?.id === c.id ? 'active' : ''}`}
                        onClick={async () => {
                          await loadChat(c.id)
                          setActiveTab('Ask AI')
                          setIsSidebarExpanded(false)
                        }}
                        title={c.title}
                      >
                        <span className="recent-dot">•</span>
                        <span className="recent-text">{c.title}</span>
                      </div>
                    ))
                  ) : (
                    <div className="gemini-recent-empty">No conversations yet</div>
                  )}
                </div>
              </div>
            )}

            {/* Expanded Bottom */}
            <div className="gemini-expanded-bottom">
              <button
                className={`gemini-expanded-nav-item ${activeTab === 'Settings' ? 'active' : ''}`}
                onClick={() => {
                  setActiveTab('Settings')
                  setIsSidebarExpanded(false)
                }}
              >
                <SettingsIcon size={17} className="expanded-nav-icon" />
                <span className="expanded-nav-label">Settings</span>
              </button>

              {/* User Profile or Sign-In in Expanded Mode */}
              {isAuthenticated && user ? (
                <div className="gemini-expanded-user-card">
                  <div className="gemini-expanded-user-left">
                    <img
                      src={user.picture || AVATARS['Olivia Rhye']}
                      alt={user.name}
                      className="gemini-avatar-img"
                      referrerPolicy="no-referrer"
                    />
                    <div className="gemini-expanded-user-text">
                      <span className="expanded-user-name">{user.name}</span>
                      <span className="expanded-user-email">{user.email}</span>
                    </div>
                  </div>
                  <button
                    className="gemini-expanded-logout-btn"
                    onClick={() => logout()}
                    title="Sign Out"
                  >
                    <LogOut size={15} />
                  </button>
                </div>
              ) : (
                <button
                  className="gemini-expanded-signin-btn"
                  onClick={() => setIsLoginModalOpen(true)}
                >
                  <GuestAvatarIcon size={18} />
                  <span>Sign in with Google</span>
                </button>
              )}
            </div>
          </div>
        )}
      </aside>

      {/* Backdrop for mobile drawer when sidebar is opened on mobile */}
      {isSidebarExpanded && (
        <div
          className="gemini-mobile-backdrop"
          onClick={() => setIsSidebarExpanded(false)}
          aria-label="Close navigation drawer"
        />
      )}

      {/* ===================== MAIN CONTENT WRAPPER ===================== */}
      <main className="main-wrapper">
        {/* Top Header */}
        <header className="top-header">
          <div className="top-header-left">
            {/* Mobile Hamburger Drawer Toggle */}
            <button
              className="mobile-sidebar-toggle-btn"
              onClick={() => setIsSidebarExpanded((prev) => !prev)}
              title="Toggle Menu"
              aria-label="Toggle Menu"
            >
              <PanelLeftOpen size={18} />
            </button>

            {/* MARVO Top Brand */}
            <div
              className="top-logo-badge"
              title="MARVO AI Knowledge Search"
              onClick={() => {
                setActiveTab('Ask AI')
                setIsSidebarExpanded(false)
              }}
            >
              <MarvoLogo size={18} className="top-brand-logo" />
              <span className="top-logo-title">MARVO</span>
              <span className="top-ai-badge">AI</span>
            </div>
          </div>

          <div className="header-right-actions">
            <button className="icon-button" title="Help & Documentation">
              <HelpCircle size={18} />
            </button>

            <button
              ref={notificationsRef}
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
                ref={headerUserDropdownRef}
                className="user-header-pill-wrapper"
                style={{ position: 'relative' }}
              >
                <div
                  className="user-header-pill"
                  onClick={() => setShowHeaderDropdown((prev) => !prev)}
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

                {showHeaderDropdown && (
                  <div className="header-user-dropdown" onClick={(e) => e.stopPropagation()}>
                    <div className="user-dropdown-header">
                      <div className="user-dropdown-name">{user.name}</div>
                      <div className="user-dropdown-email">{user.email}</div>
                      <span className="user-dropdown-role-tag">{user.role || 'Member'}</span>
                    </div>
                    <button
                      className="user-dropdown-item logout"
                      onClick={() => {
                        setShowHeaderDropdown(false)
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
        {activeTab === 'Chats' && (
          <ChatHistory
            onOpenChat={() => setActiveTab('Ask AI')}
            onNewChat={() => setActiveTab('Ask AI')}
          />
        )}
        {activeTab === 'Settings' && <Settings />}

        {/* Google Authentication Dialog */}
        <LoginModal />
      </main>
    </div>
  )
}
