import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useAuth } from './AuthContext'

const ChatContext = createContext(null)
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export function ChatProvider({ children }) {
  const { user, token, isAuthenticated, handleUnauthorized } = useAuth()
  const [chats, setChats] = useState([])
  const [isLoadingChats, setIsLoadingChats] = useState(false)
  const [activeChat, setActiveChat] = useState(null)
  const [searchFilter, setSearchFilter] = useState('')

  const getAuthHeaders = useCallback((extra = {}) => {
    const headers = { ...extra }
    if (token && typeof token === 'string' && token.trim()) {
      headers['Authorization'] = `Bearer ${token.trim()}`
    }
    return headers
  }, [token])

  const fetchUserChats = useCallback(async (query = '') => {
    if (!isAuthenticated || !token || !user) {
      setChats([])
      return
    }
    setIsLoadingChats(true)
    try {
      const params = new URLSearchParams()
      if (query) params.append('search', query)

      const res = await fetch(`${API_BASE}/api/chats?${params.toString()}`, {
        headers: getAuthHeaders()
      })
      if (res.status === 401) {
        handleUnauthorized?.()
        setChats([])
        return
      }
      if (res.ok) {
        const data = await res.json()
        setChats(data)
      }
    } catch (err) {
      console.warn('Could not load user chats:', err)
    } finally {
      setIsLoadingChats(false)
    }
  }, [isAuthenticated, token, user, getAuthHeaders, handleUnauthorized])

  useEffect(() => {
    if (isAuthenticated && token && user?.id) {
      fetchUserChats()
    } else {
      setChats([])
      setActiveChat(null)
    }
  }, [isAuthenticated, token, user?.id, fetchUserChats])

  const saveChat = useCallback(async (chatPayload) => {
    if (!isAuthenticated || !token || !user) return null
    try {
      const payload = {
        ...chatPayload,
        user_email: user.email
      }
      const res = await fetch(`${API_BASE}/api/chats`, {
        method: 'POST',
        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(payload)
      })
      if (res.status === 401) {
        handleUnauthorized?.()
        return null
      }
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
  }, [isAuthenticated, token, user, getAuthHeaders, fetchUserChats, handleUnauthorized])

  const loadChat = useCallback(async (chatId) => {
    if (!isAuthenticated || !token) return null
    try {
      const res = await fetch(`${API_BASE}/api/chats/${chatId}`, {
        headers: getAuthHeaders()
      })
      if (res.status === 401) {
        handleUnauthorized?.()
        return null
      }
      if (res.ok) {
        const data = await res.json()
        setActiveChat(data)
        return data
      }
    } catch (err) {
      console.warn('Error loading chat transcript:', err)
    }
    return null
  }, [isAuthenticated, token, getAuthHeaders, handleUnauthorized])

  const deleteChat = useCallback(async (chatId) => {
    if (!isAuthenticated || !token) return false
    try {
      const res = await fetch(`${API_BASE}/api/chats/${chatId}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      })
      if (res.status === 401) {
        handleUnauthorized?.()
        return false
      }
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
  }, [isAuthenticated, token, activeChat, getAuthHeaders, handleUnauthorized])

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
        searchFilter,
        setSearchFilter,
        fetchUserChats,
        saveChat,
        loadChat,
        deleteChat,
        startNewChat
      }}
    >
      {children}
    </ChatContext.Provider>
  )
}

export function useChat() {
  const context = useContext(ChatContext)
  if (!context) {
    throw new Error('useChat must be used within a ChatProvider')
  }
  return context
}
