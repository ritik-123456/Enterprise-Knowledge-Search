import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useAuth } from './AuthContext'

const ChatContext = createContext(null)
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export function ChatProvider({ children }) {
  const { user, isAuthenticated } = useAuth()
  const [chats, setChats] = useState([])
  const [isLoadingChats, setIsLoadingChats] = useState(false)
  const [activeChat, setActiveChat] = useState(null)
  const [searchFilter, setSearchFilter] = useState('')

  const fetchUserChats = useCallback(async (query = '') => {
    if (!isAuthenticated || !user) {
      setChats([])
      return
    }
    setIsLoadingChats(true)
    try {
      const params = new URLSearchParams()
      if (user.id) params.append('user_id', user.id)
      if (user.email) params.append('user_email', user.email)
      if (query) params.append('search', query)

      const res = await fetch(`${API_BASE}/api/chats?${params.toString()}`)
      if (res.ok) {
        const data = await res.json()
        setChats(data)
      }
    } catch (err) {
      console.warn('Could not load user chats:', err)
    } finally {
      setIsLoadingChats(false)
    }
  }, [isAuthenticated, user])

  useEffect(() => {
    if (isAuthenticated && user) {
      fetchUserChats()
    } else {
      setChats([])
      setActiveChat(null)
    }
  }, [isAuthenticated, user, fetchUserChats])

  const saveChat = useCallback(async (chatPayload) => {
    if (!isAuthenticated || !user) return null
    try {
      const payload = {
        ...chatPayload,
        user_id: user.id || user.email,
        user_email: user.email
      }
      const res = await fetch(`${API_BASE}/api/chats`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (res.ok) {
        const saved = await res.json()
        setActiveChat(saved)
        fetchUserChats()
        return saved
      }
    } catch (err) {
      console.warn('Error saving chat session:', err)
    }
    return null
  }, [isAuthenticated, user, fetchUserChats])

  const loadChat = useCallback(async (chatId) => {
    try {
      const res = await fetch(`${API_BASE}/api/chats/${chatId}`)
      if (res.ok) {
        const data = await res.json()
        setActiveChat(data)
        return data
      }
    } catch (err) {
      console.warn('Error loading chat transcript:', err)
    }
    return null
  }, [])

  const deleteChat = useCallback(async (chatId) => {
    try {
      const res = await fetch(`${API_BASE}/api/chats/${chatId}`, {
        method: 'DELETE'
      })
      if (res.ok) {
        setChats(prev => prev.filter(c => c.id !== chatId))
        if (activeChat?.id === chatId) {
          setActiveChat(null)
        }
        return true
      }
    } catch (err) {
      console.warn('Error deleting chat session:', err)
    }
    return false
  }, [activeChat])

  const startNewChat = useCallback(() => {
    setActiveChat(null)
  }, [])

  return (
    <ChatContext.Provider
      value={{
        chats,
        isLoadingChats,
        activeChat,
        setActiveChat,
        fetchUserChats,
        saveChat,
        loadChat,
        deleteChat,
        startNewChat,
        searchFilter,
        setSearchFilter
      }}
    >
      {children}
    </ChatContext.Provider>
  )
}

export function useChat() {
  const ctx = useContext(ChatContext)
  if (!ctx) {
    throw new Error('useChat must be used within a ChatProvider')
  }
  return ctx
}
