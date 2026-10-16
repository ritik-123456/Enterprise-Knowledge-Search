import { useState, useMemo, useEffect } from 'react'
import {
  Search,
  MessageSquare,
  Clock,
  Trash2,
  Plus,
  RefreshCw,
  Sparkles,
  ArrowRight,
  ArrowLeft,
  Layers,
  X,
  Copy,
  Check,
  CheckCircle2,
  User as UserIcon,
  ChevronRight
} from 'lucide-react'
import { useChat } from '../context/ChatContext'
import { useAuth } from '../context/AuthContext'
import ClaudeMarkdown, { stripChunkIdCitations } from '../components/ClaudeMarkdown'
import MarvoLogo from '../components/MarvoLogo'

export default function ChatHistory({ onOpenChat, onNewChat }) {
  const { user } = useAuth()
  const {
    chats,
    isLoadingChats,
    fetchUserChats,
    loadChat,
    deleteChat,
    startNewChat
  } = useChat()

  const [searchQuery, setSearchQuery] = useState('')
  const [selectedChatId, setSelectedChatId] = useState(null)
  const [selectedChatData, setSelectedChatData] = useState(null)
  const [isLoadingDetail, setIsLoadingDetail] = useState(false)
  const [copiedMsgId, setCopiedMsgId] = useState(null)
  const [activeSources, setActiveSources] = useState({})
  const [deletingId, setDeletingId] = useState(null)
  const [mobilePane, setMobilePane] = useState('list')

  // Filter conversations based on search term
  const filteredChats = useMemo(() => {
    if (!searchQuery.trim()) return chats
    const q = searchQuery.toLowerCase().trim()
    return chats.filter(
      c =>
        (c.title || '').toLowerCase().includes(q) ||
        (c.snippet || '').toLowerCase().includes(q)
    )
  }, [chats, searchQuery])

  // Automatically select the most recent conversation if none selected
  useEffect(() => {
    if (filteredChats.length > 0) {
      const exists = filteredChats.some(c => c.id === selectedChatId)
      if (!selectedChatId || !exists) {
        setSelectedChatId(filteredChats[0].id)
      }
    } else {
      setSelectedChatId(null)
      setSelectedChatData(null)
    }
  }, [filteredChats, selectedChatId])

  // Load the complete chat transcript when selectedChatId changes
  useEffect(() => {
    let isCancelled = false
    if (!selectedChatId) {
      setSelectedChatData(null)
      return
    }

    setIsLoadingDetail(true)
    loadChat(selectedChatId).then(data => {
      if (!isCancelled && data) {
        setSelectedChatData(data)
      }
      if (!isCancelled) {
        setIsLoadingDetail(false)
      }
    }).catch(() => {
      if (!isCancelled) setIsLoadingDetail(false)
    })

    return () => {
      isCancelled = true
    }
  }, [selectedChatId, loadChat])

  const handleSelectChat = (chatId) => {
    setSelectedChatId(chatId)
    setMobilePane('detail')
  }

  const handleResumeInAskAI = async (chatId) => {
    await loadChat(chatId)
    if (onOpenChat) {
      onOpenChat(chatId)
    }
  }

  const handleDelete = async (e, chatId) => {
    e.stopPropagation()
    if (!window.confirm('Are you sure you want to delete this chat session?')) {
      return
    }
    setDeletingId(chatId)
    try {
      await deleteChat(chatId)
      if (selectedChatId === chatId) {
        setSelectedChatId(null)
        setSelectedChatData(null)
        setMobilePane('list')
      }
    } finally {
      setDeletingId(null)
    }
  }

  const handleStartNewChat = () => {
    startNewChat()
    if (onNewChat) {
      onNewChat()
    }
  }

  const copyMessageText = (msgId, text) => {
    navigator.clipboard.writeText(stripChunkIdCitations(text || ''))
    setCopiedMsgId(msgId)
    setTimeout(() => setCopiedMsgId(null), 2000)
  }

  const formatDate = (isoString) => {
    if (!isoString) return 'Recent'
    try {
      const date = new Date(isoString)
      const now = new Date()
      const diffMs = now - date
      const diffMins = Math.floor(diffMs / 60000)
      const diffHours = Math.floor(diffMins / 60)
      const diffDays = Math.floor(diffHours / 24)

      if (diffMins < 2) return 'Just now'
      if (diffMins < 60) return `${diffMins}m ago`
      if (diffHours < 24) return `${diffHours}h ago`
      if (diffDays === 1) return 'Yesterday'
      if (diffDays < 7) return `${diffDays}d ago`
      return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
    } catch {
      return 'Recent'
    }
  }

  return (
    <div className={`llm-history-wrapper mobile-pane-${mobilePane}`}>
      {/* ===================== LEFT SIDEBAR: TOPIC HISTORY LIST ===================== */}
      <aside className="llm-history-sidebar">
        <div className="llm-sidebar-header">
          <div className="llm-sidebar-top-row">
            <span className="llm-sidebar-title">Chat History</span>
            <button
              className="llm-sync-btn"
              onClick={() => fetchUserChats(searchQuery)}
              title="Sync with Supabase"
              disabled={isLoadingChats}
            >
              <RefreshCw size={13} className={isLoadingChats ? 'spin' : ''} />
            </button>
          </div>

          <button
            className="llm-new-chat-btn"
            onClick={handleStartNewChat}
          >
            <Plus size={16} />
            <span>New Chat</span>
          </button>

          {/* Search Input for Topics */}
          <div className="llm-search-input-box">
            <Search size={14} className="llm-search-icon" />
            <input
              type="text"
              placeholder="Search chat topics..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="llm-search-input"
            />
            {searchQuery && (
              <button
                className="llm-search-clear"
                onClick={() => setSearchQuery('')}
              >
                <X size={12} />
              </button>
            )}
          </div>
        </div>

        {/* List of Chat Sessions (Titled by First Topic) */}
        <div className="llm-history-list">
          {isLoadingChats && chats.length === 0 ? (
            <div className="llm-list-loading">
              <div className="chat-spinner" />
              <span>Loading history...</span>
            </div>
          ) : filteredChats.length === 0 ? (
            <div className="llm-list-empty">
              <MessageSquare size={24} style={{ color: 'var(--text-dim)', marginBottom: 6 }} />
              {searchQuery ? (
                <span>No topics matched your search</span>
              ) : (
                <span>No conversation history yet. Start a new chat!</span>
              )}
            </div>
          ) : (
            filteredChats.map((chat) => {
              const isSelected = chat.id === selectedChatId
              return (
                <div
                  key={chat.id}
                  className={`llm-history-item ${isSelected ? 'active' : ''}`}
                  onClick={() => handleSelectChat(chat.id)}
                >
                  <div className="llm-item-icon">
                    <MessageSquare size={15} />
                  </div>
                  <div className="llm-item-content">
                    {/* Header = First Topic of the Chat */}
                    <div className="llm-item-topic" title={chat.title}>
                      {chat.title}
                    </div>
                    <div className="llm-item-meta">
                      <span>{formatDate(chat.updated_at || chat.created_at)}</span>
                      <span>•</span>
                      <span>{chat.message_count} {chat.message_count === 1 ? 'msg' : 'msgs'}</span>
                    </div>
                  </div>
                  <button
                    className="llm-item-delete"
                    onClick={(e) => handleDelete(e, chat.id)}
                    title="Delete conversation"
                    disabled={deletingId === chat.id}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              )
            })
          )}
        </div>
      </aside>

      {/* ===================== RIGHT MAIN PANE: COMPLETE CHAT VIEW ===================== */}
      <main className="llm-history-main">
        {isLoadingDetail && !selectedChatData ? (
          <div className="llm-detail-loading">
            <div className="chat-spinner" />
            <span>Loading complete conversation...</span>
          </div>
        ) : selectedChatData ? (
          <div className="llm-chat-container">
            {/* TOP HEADER: FIRST TOPIC OF THE CHAT */}
            <header className="llm-chat-header">
              <div className="llm-chat-header-left">
                <button
                  type="button"
                  className="mobile-back-to-list-btn"
                  onClick={() => setMobilePane('list')}
                  title="Back to conversation list"
                >
                  <ArrowLeft size={14} />
                  <span>All Chats</span>
                </button>
                <div className="llm-topic-tag">
                  <Sparkles size={13} />
                  <span>Conversation Session</span>
                </div>
                {/* FIRST TOPIC AS MAIN HEADER */}
                <h1 className="llm-chat-main-topic">
                  {selectedChatData.title}
                </h1>
                <div className="llm-chat-header-meta">
                  <span className="meta-item">
                    <Clock size={12} />
                    <span>Created {formatDate(selectedChatData.created_at)}</span>
                  </span>
                  <span className="meta-dot">•</span>
                  <span className="meta-item">
                    <Layers size={12} />
                    <span>{(selectedChatData.messages || []).length} messages</span>
                  </span>
                </div>
              </div>

              <div className="llm-chat-header-actions">
                <button
                  className="llm-resume-chat-btn"
                  onClick={() => handleResumeInAskAI(selectedChatData.id)}
                  title="Open this conversation in Ask AI to continue asking questions"
                >
                  <span>Continue in Ask AI</span>
                  <ArrowRight size={15} />
                </button>
                <button
                  className="llm-header-delete-btn"
                  onClick={(e) => handleDelete(e, selectedChatData.id)}
                  title="Delete this chat"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </header>

            {/* INSIDE: THE COMPLETE CHAT TRANSCRIPT */}
            <div className="llm-chat-thread-body">
              {(selectedChatData.messages || []).length === 0 ? (
                <div className="llm-no-messages">
                  <p>No messages recorded in this conversation.</p>
                </div>
              ) : (
                selectedChatData.messages.map((msg, index) => {
                  const isUser = msg.role === 'user'

                  if (isUser) {
                    return (
                      <div key={msg.id || index} className="claude-user-message-row">
                        <div className="claude-user-bubble">
                          <div className="claude-user-bubble-header">
                            <div className="claude-user-identity">
                              <div className="claude-user-avatar-circle">
                                {user?.picture ? (
                                  <img
                                    src={user.picture}
                                    alt={user.name || 'User'}
                                    className="claude-user-avatar-img"
                                  />
                                ) : (
                                  <UserIcon size={14} />
                                )}
                              </div>
                              <span className="claude-user-label">{user?.name || 'You'}</span>
                              <span className="claude-user-time">{msg.timestamp || 'Message'}</span>
                            </div>

                            <button
                              type="button"
                              className="claude-user-copy-btn"
                              onClick={() => copyMessageText(msg.id, msg.text)}
                              title="Copy prompt text"
                            >
                              {copiedMsgId === msg.id ? (
                                <Check size={12} style={{ color: '#10b981' }} />
                              ) : (
                                <Copy size={12} />
                              )}
                            </button>
                          </div>
                          <div className="claude-user-query-text">{msg.text}</div>
                        </div>
                      </div>
                    )
                  }

                  // Assistant Turn inside Complete Chat
                  const answerText = msg.data?.answer || msg.data?.lead || msg.text || ''
                  const keyPoints = msg.data?.keyPoints || []
                  const stats = msg.data?.stats
                  const sources = msg.data?.sources || []
                  const activeSrcId = activeSources[msg.id]
                  const activeSrc = sources.find(s => String(s.id) === String(activeSrcId))

                  return (
                    <div key={msg.id || index} className="claude-assistant-message-row">
                      <div className="claude-assistant-avatar" style={{ background: 'transparent', boxShadow: 'none' }}>
                        <MarvoLogo size={28} />
                      </div>

                      <div className="claude-assistant-container">
                        <div className="claude-assistant-header">
                          <div className="claude-assistant-identity">
                            <span className="claude-assistant-name">MARVO AI</span>
                            <span className="claude-assistant-badge">Enterprise Engine</span>
                          </div>
                          {stats && (
                            <span className="claude-assistant-meta">
                              {stats.responseTime} • {stats.sourcesUsed} sources verified
                            </span>
                          )}
                        </div>

                        {/* Complete Answer Markdown */}
                        <div className="claude-answer-stream">
                          <ClaudeMarkdown
                            content={answerText}
                            onCitationClick={(num) =>
                              setActiveSources(prev => ({
                                ...prev,
                                [msg.id]: prev[msg.id] === num ? null : num
                              }))
                            }
                          />

                          {/* Key Points Bullet List */}
                          {keyPoints.length > 0 && (
                            <div className="claude-key-points-box">
                              <span className="claude-key-points-title">Key Takeaways</span>
                              <ul className="claude-key-points-list">
                                {keyPoints.map((point, pIdx) => (
                                  <li key={pIdx} className="claude-key-point-item">
                                    <ClaudeMarkdown content={point} />
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* Cited Sources Shelf */}
                          {sources.length > 0 && (
                            <div className="claude-sources-shelf">
                              <span className="claude-sources-shelf-label">Cited Documents:</span>
                              <div className="claude-sources-pills-row">
                                {sources.map(src => (
                                  <button
                                    key={src.id}
                                    type="button"
                                    className={`claude-source-pill ${activeSrcId === src.id ? 'active' : ''}`}
                                    onClick={() =>
                                      setActiveSources(prev => ({
                                        ...prev,
                                        [msg.id]: prev[msg.id] === src.id ? null : src.id
                                      }))
                                    }
                                  >
                                    <span className="claude-source-num">[{src.id}]</span>
                                    <span className="claude-source-name">{src.source_name}</span>
                                    <span className="claude-source-page">{src.page}</span>
                                  </button>
                                ))}
                              </div>

                              {activeSrc && (
                                <div className="claude-source-preview-box">
                                  <div className="claude-source-preview-header">
                                    <span className="claude-source-preview-title">
                                      <CheckCircle2 size={12} style={{ color: '#10b981' }} />
                                      <span>[{activeSrc.id}] {activeSrc.source_name} • {activeSrc.page}</span>
                                    </span>
                                    <button
                                      type="button"
                                      className="claude-source-preview-close"
                                      onClick={() => setActiveSources(prev => ({ ...prev, [msg.id]: null }))}
                                      title="Close snippet preview"
                                    >
                                      <X size={13} />
                                    </button>
                                  </div>
                                  <p className="claude-source-preview-snippet">"{activeSrc.snippet}"</p>
                                </div>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Copy Action */}
                        <div className="claude-actions-toolbar" style={{ marginTop: '4px' }}>
                          <button
                            type="button"
                            className="claude-ghost-btn"
                            onClick={() => copyMessageText(msg.id, answerText)}
                            title="Copy response"
                          >
                            {copiedMsgId === msg.id ? (
                              <>
                                <Check size={13} style={{ color: '#10b981' }} />
                                <span style={{ color: '#10b981' }}>Copied</span>
                              </>
                            ) : (
                              <>
                                <Copy size={13} />
                                <span>Copy</span>
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                })
              )}
            </div>

            {/* Bottom Floating Bar to Continue Asking */}
            <div className="llm-chat-bottom-dock">
              <button
                className="llm-dock-resume-btn"
                onClick={() => handleResumeInAskAI(selectedChatData.id)}
              >
                <Sparkles size={16} />
                <span>Continue this conversation in Ask AI</span>
                <ArrowRight size={16} />
              </button>
            </div>
          </div>
        ) : (
          <div className="llm-empty-selection">
            <div className="empty-state-icon-wrap">
              <MessageSquare size={36} />
            </div>
            <h2>Select a conversation</h2>
            <p>Choose any conversation topic from the sidebar to inspect the complete chat history.</p>
            <button className="chat-action-btn primary" onClick={handleStartNewChat}>
              <Plus size={16} />
              <span>Start New Chat</span>
            </button>
          </div>
        )}
      </main>
    </div>
  )
}
