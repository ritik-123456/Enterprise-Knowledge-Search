import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Sparkles,
  Paperclip,
  RotateCcw,
  Copy,
  Check,
  ThumbsUp,
  ThumbsDown,
  Bookmark,
  FileText,
  X,
  Trash2,
  AlertCircle,
  CheckCircle2,
  Loader2,
  SearchX,
  Filter,
  RefreshCw,
  FolderOpen,
  ChevronDown,
  Square,
  Layers,
  Plus
} from 'lucide-react'
import ClaudeMarkdown, { stripChunkIdCitations } from '../components/ClaudeMarkdown'
import { useChat } from '../context/ChatContext'
import { useAuth } from '../context/AuthContext'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const STARTER_PROMPTS = [
  {
    query: 'What is our remote work policy?',
    desc: 'Core hours, remote days per week, and manager approvals'
  },
  {
    query: 'How do I request budget approval?',
    desc: 'Procurement thresholds, VP signoffs, and finance guidelines'
  },
  {
    query: 'What tools do we use for analytics?',
    desc: 'Data warehouse, telemetry tracking, and BI dashboards'
  },
  {
    query: 'Where can I find the OKR process?',
    desc: 'Quarterly cadence, Notion workspaces, and grading criteria'
  }
]

export default function AskAI() {
  const { user, token, isAuthenticated, handleUnauthorized, openLoginModal, registerResetHook } = useAuth()
  const { activeChat, saveChat, startNewChat } = useChat()
  const [currentChatId, setCurrentChatId] = useState(null)

  // Auth header helper strictly scoped to verified bearer token (omitted when logged out, never X-User-Id)
  const getAuthHeaders = useCallback((extra = {}) => {
    const headers = { ...extra }
    if (token && typeof token === 'string' && token.trim()) {
      headers['Authorization'] = `Bearer ${token.trim()}`
    }
    return headers
  }, [token])

  // Query & Ask States
  const [inputVal, setInputVal] = useState('')
  const [currentQuestion, setCurrentQuestion] = useState('')
  const [hasSearched, setHasSearched] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [searchError, setSearchError] = useState(null)
  const [answerData, setAnswerData] = useState(null)

  // Claude Conversation Thread & Interaction States
  const [threadMessages, setThreadMessages] = useState([])
  const [activeSources, setActiveSources] = useState({}) // { [msgId]: sourceId | null }
  const [messageFeedback, setMessageFeedback] = useState({}) // { [msgId]: 'good' | 'bad' | null }
  const [copiedMsgId, setCopiedMsgId] = useState(null)
  const [bookmarkedMsgs, setBookmarkedMsgs] = useState({}) // { [msgId]: boolean }

  // Synchronize conversation state when a chat is selected from Chat History or New Chat is initiated
  useEffect(() => {
    if (activeChat && activeChat.messages && activeChat.messages.length > 0) {
      setThreadMessages(activeChat.messages)
      setCurrentChatId(activeChat.id)
      setHasSearched(true)
      const lastMsg = activeChat.messages[activeChat.messages.length - 1]
      if (lastMsg && lastMsg.role === 'assistant') {
        setAnswerData(lastMsg.data)
      }
    } else if (!activeChat) {
      setThreadMessages([])
      setCurrentChatId(null)
      setHasSearched(false)
      setAnswerData(null)
    }
  }, [activeChat])

  // Document Filtering (optional document_id on ask)
  const [selectedDocId, setSelectedDocId] = useState('')

  // Document Management States
  const [documents, setDocuments] = useState([])
  const [isDocsLoading, setIsDocsLoading] = useState(false)
  const [docsError, setDocsError] = useState(null)
  const [showDocsPanel, setShowDocsPanel] = useState(false)
  const [deletingDocId, setDeletingDocId] = useState(null)

  // Real-Time Upload Tracking States
  const [uploads, setUploads] = useState([])
  const [fileError, setFileError] = useState('')
  const activePollersRef = useRef(new Map())
  const docsAbortControllerRef = useRef(null)
  const askAbortControllerRef = useRef(null)
  const currentUserIdRef = useRef(user?.id)
  const allDocsRef = useRef(null)

  // Close "All Documents" dropdown when clicking outside or pressing Escape
  useEffect(() => {
    if (!showDocsPanel) return
    const handleClickOutside = (e) => {
      if (allDocsRef.current && !allDocsRef.current.contains(e.target)) {
        setShowDocsPanel(false)
      }
    }
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setShowDocsPanel(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [showDocsPanel])

  // Track if any PDF is currently uploading or processing in the background
  const isUploadingOrProcessing = uploads.some(
    u => u.status === 'uploading' || u.status === 'processing'
  )

  useEffect(() => {
    currentUserIdRef.current = user?.id
  }, [user?.id])

  // UI Micro-interactions
  const [feedback, setFeedback] = useState(null)
  const [copied, setCopied] = useState(false)
  const [bookmarked, setBookmarked] = useState(false)
  const [glowKey, setGlowKey] = useState(0)
  const [isGlowActive, setIsGlowActive] = useState(false)

  const fileInputRef = useRef(null)
  const threadBottomRef = useRef(null)

  const triggerAiGlow = () => {
    setGlowKey(prev => prev + 1)
    setIsGlowActive(true)
  }

  // Smooth scroll to latest response in active conversation thread
  useEffect(() => {
    if (hasSearched) {
      setTimeout(() => {
        threadBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 60)
    }
  }, [hasSearched, isGenerating, threadMessages])

  // -------------------------------------------------------------
  // 1. DOCUMENT REPOSITORY SYNC (GET /api/documents)
  // -------------------------------------------------------------
  const fetchDocuments = useCallback(async () => {
    if (!token || !isAuthenticated || !user?.id) {
      setDocuments([])
      return
    }

    if (docsAbortControllerRef.current) {
      docsAbortControllerRef.current.abort()
    }
    const controller = new AbortController()
    docsAbortControllerRef.current = controller
    const requestedUserId = user?.id

    setIsDocsLoading(true)
    setDocsError(null)
    try {
      const res = await fetch(`${API_BASE}/api/documents`, {
        headers: getAuthHeaders(),
        signal: controller.signal
      })
      if (controller.signal.aborted || currentUserIdRef.current !== requestedUserId) {
        return
      }
      if (res.status === 401) {
        handleUnauthorized?.()
        setDocuments([])
        return
      }
      if (res.ok) {
        const data = await res.json()
        if (!controller.signal.aborted && currentUserIdRef.current === requestedUserId) {
          setDocuments(data)
        }
      } else {
        if (!controller.signal.aborted && currentUserIdRef.current === requestedUserId) {
          setDocsError(`Unable to fetch document list (${res.status})`)
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') return
      if (!controller.signal.aborted && currentUserIdRef.current === requestedUserId) {
        setDocsError('Backend server is currently offline.')
      }
    } finally {
      if (!controller.signal.aborted && currentUserIdRef.current === requestedUserId) {
        setIsDocsLoading(false)
      }
    }
  }, [token, isAuthenticated, user?.id, getAuthHeaders, handleUnauthorized])

  // Reset ALL per-user UI states whenever user?.id changes or becomes null
  useEffect(() => {
    if (docsAbortControllerRef.current) {
      docsAbortControllerRef.current.abort()
      docsAbortControllerRef.current = null
    }
    if (askAbortControllerRef.current) {
      askAbortControllerRef.current.abort()
      askAbortControllerRef.current = null
    }

    activePollersRef.current.forEach((intervalId) => clearInterval(intervalId))
    activePollersRef.current.clear()

    setDocuments([])
    setSelectedDocId('')
    setUploads([])
    setAnswerData(null)
    setActiveSources({})
    setThreadMessages([])
    setInputVal('')
    setCurrentQuestion('')
    setHasSearched(false)
    setIsGenerating(false)
    setSearchError(null)
    setDocsError(null)
    setFileError('')
    setCurrentChatId(null)
    setMessageFeedback({})
    setBookmarkedMsgs({})
    setCopiedMsgId(null)
    setDeletingDocId(null)

    if (user?.id && token) {
      fetchDocuments()
    }

    return () => {
      if (docsAbortControllerRef.current) {
        docsAbortControllerRef.current.abort()
      }
      if (askAbortControllerRef.current) {
        askAbortControllerRef.current.abort()
      }
      activePollersRef.current.forEach((intervalId) => clearInterval(intervalId))
      activePollersRef.current.clear()
    }
  }, [user?.id, token, fetchDocuments])

  // Explicit logout hook reset
  useEffect(() => {
    if (!registerResetHook) return
    const unregister = registerResetHook(() => {
      if (docsAbortControllerRef.current) {
        docsAbortControllerRef.current.abort()
        docsAbortControllerRef.current = null
      }
      if (askAbortControllerRef.current) {
        askAbortControllerRef.current.abort()
        askAbortControllerRef.current = null
      }
      activePollersRef.current.forEach((intervalId) => clearInterval(intervalId))
      activePollersRef.current.clear()

      setDocuments([])
      setSelectedDocId('')
      setUploads([])
      setAnswerData(null)
      setActiveSources({})
      setThreadMessages([])
      setInputVal('')
      setCurrentQuestion('')
      setHasSearched(false)
      setIsGenerating(false)
      setSearchError(null)
      setDocsError(null)
      setFileError('')
      setCurrentChatId(null)
      setMessageFeedback({})
      setBookmarkedMsgs({})
      setCopiedMsgId(null)
      setDeletingDocId(null)
    })
    return unregister
  }, [registerResetHook])

  // -------------------------------------------------------------
  // 2. REAL-TIME UPLOADS & POLLING STATUS (GET /api/documents/{id}/status)
  // -------------------------------------------------------------
  const pollDocumentStatus = useCallback((tempUploadId, docId, uploadUserId) => {
    if (activePollersRef.current.has(tempUploadId)) {
      clearInterval(activePollersRef.current.get(tempUploadId))
    }

    let attempts = 0
    const maxAttempts = 60

    const intervalId = setInterval(async () => {
      // Poller guard: stop and discard if current user ID no longer matches the user when upload started
      if (!currentUserIdRef.current || currentUserIdRef.current !== uploadUserId) {
        clearInterval(intervalId)
        activePollersRef.current.delete(tempUploadId)
        return
      }

      attempts += 1
      if (attempts > maxAttempts) {
        clearInterval(intervalId)
        activePollersRef.current.delete(tempUploadId)
        if (currentUserIdRef.current === uploadUserId) {
          setUploads(prev =>
            prev.map(u =>
              u.id === tempUploadId
                ? { ...u, status: 'failed', errorReason: 'Processing timed out after 90 seconds' }
                : u
            )
          )
        }
        return
      }

      try {
        const res = await fetch(`${API_BASE}/api/documents/${docId}/status`, {
          headers: getAuthHeaders()
        })
        if (!currentUserIdRef.current || currentUserIdRef.current !== uploadUserId) {
          clearInterval(intervalId)
          activePollersRef.current.delete(tempUploadId)
          return
        }
        if (res.status === 401) {
          clearInterval(intervalId)
          activePollersRef.current.delete(tempUploadId)
          handleUnauthorized?.()
          return
        }
        if (res.ok) {
          const data = await res.json()
          if (!currentUserIdRef.current || currentUserIdRef.current !== uploadUserId) {
            clearInterval(intervalId)
            activePollersRef.current.delete(tempUploadId)
            return
          }
          if (data.status === 'ready') {
            clearInterval(intervalId)
            activePollersRef.current.delete(tempUploadId)
            setUploads(prev =>
              prev.map(u => (u.id === tempUploadId ? { ...u, status: 'ready' } : u))
            )
            fetchDocuments()
          } else if (data.status === 'failed') {
            clearInterval(intervalId)
            activePollersRef.current.delete(tempUploadId)
            setUploads(prev =>
              prev.map(u =>
                u.id === tempUploadId
                  ? { ...u, status: 'failed', errorReason: data.reason || 'Processing failed' }
                  : u
              )
            )
          }
        }
      } catch {
        // Continue polling
      }
    }, 1500)

    activePollersRef.current.set(tempUploadId, intervalId)
  }, [fetchDocuments, getAuthHeaders, handleUnauthorized])

  const uploadFile = async (file) => {
    if (!isAuthenticated || !token) {
      openLoginModal("Sign in with Google to upload and search your private documents.")
      return
    }

    const uploadUserId = user?.id
    const tempId = `upl-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`
    const newUpload = {
      id: tempId,
      name: file.name,
      size: file.size,
      status: 'uploading',
      documentId: null,
      errorReason: null
    }

    setUploads(prev => [newUpload, ...prev])

    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await fetch(`${API_BASE}/api/documents/upload`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData
      })

      // Poller / upload guard: discard if user changed during upload
      if (!currentUserIdRef.current || currentUserIdRef.current !== uploadUserId) {
        return
      }

      if (res.status === 401) {
        setUploads(prev => prev.filter(u => u.id !== tempId))
        handleUnauthorized?.()
        return
      }

      if (!res.ok) {
        let reason = `Upload failed with HTTP ${res.status}`
        if (res.status === 413) reason = 'File is too large (exceeds max size limit)'
        else if (res.status === 400) reason = 'Invalid file format or corrupted PDF header'
        else if (res.status === 422) reason = 'Unreadable or scanned image-only PDF'
        else if (res.status === 429) reason = 'Upload rate limit exceeded. Please wait a moment.'

        try {
          const errData = await res.json()
          if (errData.detail) reason = errData.detail
        } catch {
          // Ignore
        }

        setUploads(prev =>
          prev.map(u => (u.id === tempId ? { ...u, status: 'failed', errorReason: reason } : u))
        )
        return
      }

      const data = await res.json()
      const assignedDocId = data.document_id

      if (data.status === 'ready') {
        setUploads(prev =>
          prev.map(u => (u.id === tempId ? { ...u, status: 'ready', documentId: assignedDocId } : u))
        )
        fetchDocuments()
      } else {
        setUploads(prev =>
          prev.map(u =>
            u.id === tempId
              ? { ...u, status: 'processing', documentId: assignedDocId }
              : u
          )
        )
        pollDocumentStatus(tempId, assignedDocId, uploadUserId)
      }
    } catch {
      if (!currentUserIdRef.current || currentUserIdRef.current !== uploadUserId) {
        return
      }
      setUploads(prev =>
        prev.map(u =>
          u.id === tempId
            ? { ...u, status: 'failed', errorReason: 'Network connection failed' }
            : u
        )
      )
    }
  }

  const handleFileChange = (e) => {
    if (!isAuthenticated || !token) {
      openLoginModal("Sign in with Google to upload and search your private documents.")
      e.target.value = ''
      return
    }

    if (e.target.files && e.target.files.length > 0) {
      const filesArray = Array.from(e.target.files)
      const pdfFiles = filesArray.filter(
        file => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
      )
      const rejectedCount = filesArray.length - pdfFiles.length

      if (rejectedCount > 0) {
        setFileError(
          `Only PDF files are supported (${rejectedCount} non-PDF file${rejectedCount > 1 ? 's were' : ' was'
          } skipped).`
        )
        setTimeout(() => setFileError(''), 4500)
      } else {
        setFileError('')
      }

      pdfFiles.forEach(f => uploadFile(f))
      e.target.value = ''
    }
  }

  const handleDismissUpload = (uploadId, e) => {
    e.stopPropagation()
    if (activePollersRef.current.has(uploadId)) {
      clearInterval(activePollersRef.current.get(uploadId))
      activePollersRef.current.delete(uploadId)
    }
    setUploads(prev => prev.filter(u => u.id !== uploadId))
  }

  // -------------------------------------------------------------
  // 3. DELETE DOCUMENT (DELETE /api/documents/{id})
  // -------------------------------------------------------------
  const handleDeleteDocument = async (docId, e) => {
    e.stopPropagation()
    if (!isAuthenticated || !token) {
      openLoginModal("Sign in with Google to manage your documents.")
      return
    }

    if (!window.confirm('Delete this document and purge all its indexed vector chunks?')) {
      return
    }

    setDeletingDocId(docId)
    try {
      const res = await fetch(`${API_BASE}/api/documents/${docId}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      })

      if (res.status === 401) {
        handleUnauthorized?.()
        return
      }

      if (res.ok) {
        setDocuments(prev => prev.filter(d => d.id !== docId))
        if (selectedDocId === docId) {
          setSelectedDocId('')
        }
        setUploads(prev => prev.filter(u => u.documentId !== docId))
      } else {
        const errData = await res.json().catch(() => ({}))
        alert(errData.detail || `Failed to delete document (${res.status})`)
      }
    } catch {
      alert('Network error while deleting document.')
    } finally {
      setDeletingDocId(null)
    }
  }

  // -------------------------------------------------------------
  // 4. FORMATTERS & STRENGTH HELPERS (No Probability Display)
  // -------------------------------------------------------------
  const getRetrievalStrengthLabel = (score) => {
    if (typeof score !== 'number') return 'High'
    if (score >= 0.72) return 'High'
    if (score >= 0.45) return 'Moderate'
    return 'Low'
  }

  const formatResponseTime = (val) => {
    if (!val) return '0.00s'
    if (typeof val === 'string') {
      const trimmed = val.trim()
      if (trimmed.endsWith('s')) {
        const num = parseFloat(trimmed)
        return isNaN(num) ? trimmed : `${num.toFixed(2)}s`
      }
      const num = parseFloat(trimmed)
      return isNaN(num) ? `${trimmed}s` : `${num.toFixed(2)}s`
    }
    if (typeof val === 'number') {
      return `${val.toFixed(2)}s`
    }
    return '0.00s'
  }

  const formatFileSize = (bytes) => {
    if (!bytes || bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }

  // -------------------------------------------------------------
  // 5. QUERY RAG PIPELINE (POST /api/documents/ask)
  // -------------------------------------------------------------
  const handleStopExecution = useCallback(() => {
    if (askAbortControllerRef.current) {
      askAbortControllerRef.current.abort()
      askAbortControllerRef.current = null
    }
    setIsGenerating(false)
    setThreadMessages(prev =>
      prev.map(m =>
        m.isGenerating
          ? {
              ...m,
              isGenerating: false,
              data: m.data?.answer ? m.data : null,
              error: 'Generation stopped by user.'
            }
          : m
      )
    )
  }, [])

  const handleAskQuestion = async (queryOverride) => {
    // Pause asking while documents are actively uploading or processing
    if (isUploadingOrProcessing) {
      return
    }

    const questionText = (queryOverride || inputVal).trim()
    if (!questionText) return

    if (!isAuthenticated || !token) {
      openLoginModal("Sign in with Google to upload and search your private documents.")
      return
    }

    if (askAbortControllerRef.current) {
      askAbortControllerRef.current.abort()
    }
    const controller = new AbortController()
    askAbortControllerRef.current = controller

    const userMsgId = `u-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`
    const assistantMsgId = `a-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

    const newUserMsg = {
      id: userMsgId,
      role: 'user',
      text: questionText,
      docScope: activeFilteredDoc?.name,
      timestamp
    }

    const newAssistantMsg = {
      id: assistantMsgId,
      role: 'assistant',
      isGenerating: true,
      data: null,
      error: null,
      timestamp
    }

    setThreadMessages(prev => [...prev, newUserMsg, newAssistantMsg])
    setIsGenerating(true)
    setHasSearched(true)
    setCurrentQuestion(questionText)
    setSearchError(null)
    setFeedback(null)
    setCopied(false)
    setInputVal('') // Clear input box once submitted, just like Claude

    try {
      const payload = { question: questionText }
      if (selectedDocId) {
        payload.document_id = selectedDocId
      }

      // Stream tokens word-by-word via Server-Sent Events (SSE)
      const res = await fetch(`${API_BASE}/api/documents/ask?stream=true`, {
        method: 'POST',
        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(payload),
        signal: controller.signal
      })

      if (controller.signal.aborted) {
        return
      }

      if (res.status === 401) {
        handleUnauthorized?.()
        setIsGenerating(false)
        setThreadMessages(prev => prev.filter(m => m.id !== assistantMsgId && m.id !== userMsgId))
        return
      }

      if (res.status === 404) {
        const err = 'The specified document ID was not found in the vector store.'
        setSearchError(err)
        setThreadMessages(prev =>
          prev.map(m =>
            m.id === assistantMsgId
              ? { ...m, isGenerating: false, data: null, error: err }
              : m
          )
        )
        return
      }

      if (!res.ok) {
        let detail = `Query failed with status ${res.status}`
        try {
          const errData = await res.json()
          if (errData.detail) detail = errData.detail
        } catch {
          // Ignore
        }
        setSearchError(detail)
        setThreadMessages(prev =>
          prev.map(m =>
            m.id === assistantMsgId
              ? { ...m, isGenerating: false, data: null, error: detail }
              : m
          )
        )
        return
      }

      // If response body is a readable stream, consume SSE tokens
      if (res.body && res.body.getReader) {
        const reader = res.body.getReader()
        const decoder = new TextDecoder('utf-8')
        let buffer = ''
        let accumulatedRawAnswer = ''
        let finalDoneData = null
        let streamError = null

        const processLine = (line) => {
          const trimmed = line.trim()
          if (!trimmed || !trimmed.startsWith('data:')) return
          const jsonStr = trimmed.replace(/^data:\s*/, '').trim()
          if (!jsonStr) return

          try {
            const eventData = JSON.parse(jsonStr)
            if (eventData.type === 'token') {
              accumulatedRawAnswer += eventData.token
              const cleanLiveText = stripChunkIdCitations(accumulatedRawAnswer)
              setThreadMessages(prev =>
                prev.map(m =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        isGenerating: true,
                        data: {
                          answerable: true,
                          answer: cleanLiveText,
                          lead: cleanLiveText,
                          keyPoints: [],
                          stats: null,
                          sources: []
                        }
                      }
                    : m
                )
              )
            } else if (eventData.type === 'done') {
              finalDoneData = eventData
            } else if (eventData.type === 'error') {
              streamError = eventData.error || 'AI generation failed.'
            }
          } catch (e) {
            console.warn('Failed to parse SSE line:', jsonStr, e)
          }
        }

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          for (const line of lines) {
            processLine(line)
          }
        }

        if (buffer.trim()) {
          processLine(buffer)
        }

        if (controller.signal.aborted) return

        if (streamError) {
          setSearchError(streamError)
          setThreadMessages(prev =>
            prev.map(m =>
              m.id === assistantMsgId
                ? { ...m, isGenerating: false, data: null, error: streamError }
                : m
            )
          )
          return
        }

        const sourceData = finalDoneData || {
          answerable: true,
          answer: accumulatedRawAnswer,
          lead: accumulatedRawAnswer,
          key_points: [],
          sources: [],
          response_time: '0.0s'
        }

        const cleanAnswer = stripChunkIdCitations(sourceData.answer || accumulatedRawAnswer)
        const cleanLead = stripChunkIdCitations(sourceData.lead || cleanAnswer)
        const cleanKeyPoints = (sourceData.key_points || []).map(p => stripChunkIdCitations(p))

        const parsed = {
          answerable: sourceData.answerable !== false,
          answer: cleanAnswer,
          lead: cleanLead,
          keyPoints: cleanKeyPoints,
          stats: {
            responseTime: formatResponseTime(sourceData.response_time),
            sourcesUsed: sourceData.sources_used || (sourceData.sources ? sourceData.sources.length : 0),
            retrievalStrength: getRetrievalStrengthLabel(sourceData.confidence)
          },
          sources: (sourceData.sources || []).map(s => ({
            id: s.id,
            source_name: s.source_name || 'Document',
            page: s.page_display || (s.page_start && s.page_end && s.page_start !== s.page_end ? `Pages ${s.page_start}-${s.page_end}` : `Page ${s.page_start || s.page || 1}`),
            page_start: s.page_start,
            page_end: s.page_end,
            snippet: s.snippet
          }))
        }

        setAnswerData(parsed)
        setThreadMessages(prev => {
          const updated = prev.map(m =>
            m.id === assistantMsgId
              ? { ...m, isGenerating: false, data: parsed, error: null }
              : m
          )
          const firstQuestion = updated.find(m => m.role === 'user')?.text || questionText
          const assignedId = currentChatId || `chat_${Date.now()}`
          if (!currentChatId) setCurrentChatId(assignedId)

          saveChat({
            id: assignedId,
            title: firstQuestion.slice(0, 100),
            messages: updated
          })

          return updated
        })
        return
      } else {
        // Fallback for non-streaming response body
        const data = await res.json()
        if (controller.signal.aborted) return

        const cleanAnswer = stripChunkIdCitations(data.answer)
        const cleanLead = stripChunkIdCitations(data.lead)
        const cleanKeyPoints = (data.key_points || []).map(p => stripChunkIdCitations(p))

        const parsed = {
          answerable: data.answerable !== false,
          answer: cleanAnswer,
          lead: cleanLead,
          keyPoints: cleanKeyPoints,
          stats: {
            responseTime: formatResponseTime(data.response_time),
            sourcesUsed: data.sources_used || (data.sources ? data.sources.length : 0),
            retrievalStrength: getRetrievalStrengthLabel(data.confidence)
          },
          sources: (data.sources || []).map(s => ({
            id: s.id,
            source_name: s.source_name || 'Document',
            page: s.page_display || (s.page_start && s.page_end && s.page_start !== s.page_end ? `Pages ${s.page_start}-${s.page_end}` : `Page ${s.page_start || s.page || 1}`),
            page_start: s.page_start,
            page_end: s.page_end,
            snippet: s.snippet
          }))
        }

        setAnswerData(parsed)
        setThreadMessages(prev => {
          const updated = prev.map(m =>
            m.id === assistantMsgId
              ? { ...m, isGenerating: false, data: parsed, error: null }
              : m
          )
          const firstQuestion = updated.find(m => m.role === 'user')?.text || questionText
          const assignedId = currentChatId || `chat_${Date.now()}`
          if (!currentChatId) setCurrentChatId(assignedId)

          saveChat({
            id: assignedId,
            title: firstQuestion.slice(0, 100),
            messages: updated
          })

          return updated
        })
        return
      }
    } catch (err) {
      if (err?.name === 'AbortError' || controller.signal.aborted) {
        return
      }
      const netErr = 'Unable to connect to the knowledge backend at http://localhost:8000.'
      setSearchError(netErr)
      setThreadMessages(prev =>
        prev.map(m =>
          m.id === assistantMsgId
            ? { ...m, isGenerating: false, data: null, error: netErr }
            : m
        )
      )
    } finally {
      if (askAbortControllerRef.current === controller) {
        askAbortControllerRef.current = null
      }
      setIsGenerating(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (isGenerating || isUploadingOrProcessing) return
      handleAskQuestion()
    }
  }

  const handleCopy = () => {
    if (!answerData) return
    const primaryText = answerData.answer || answerData.lead
    const text = stripChunkIdCitations(
      primaryText || (answerData.keyPoints || []).map(p => `• ${p}`).join('\n')
    )
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleResetSearch = () => {
    setHasSearched(false)
    setThreadMessages([])
    setCurrentQuestion('')
    setAnswerData(null)
    setSearchError(null)
    setInputVal('')
    setFeedback(null)
    setCopied(false)
    setActiveSources({})
    setMessageFeedback({})
    setCopiedMsgId(null)
    setBookmarkedMsgs({})
    setCurrentChatId(null)
    startNewChat()
  }

  const activeFilteredDoc = documents.find(d => d.id === selectedDocId)

  // -------------------------------------------------------------
  // REUSABLE SUB-COMPONENTS
  // -------------------------------------------------------------
  const renderDocumentManagerPanel = () => (
    <>
      <div className="all-docs-backdrop" onClick={() => setShowDocsPanel(false)} />
      <div className="docs-manager-panel" onClick={(e) => e.stopPropagation()}>
        <div className="docs-panel-header">
        <div className="docs-panel-title-group">
          <Layers size={16} style={{ color: 'var(--accent-blue)' }} />
          <span className="docs-panel-title">All Documents ({documents.length})</span>
        </div>
        <div className="docs-panel-actions">
          <button
            type="button"
            className="icon-action-btn"
            onClick={fetchDocuments}
            title="Refresh documents list"
            disabled={isDocsLoading}
          >
            <RefreshCw size={13} className={isDocsLoading ? 'spin-icon' : ''} />
          </button>
          <button
            type="button"
            className="icon-action-btn"
            onClick={() => setShowDocsPanel(false)}
            title="Close panel"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Global Scope: Search All Documents */}
      <div
        className={`all-docs-scope-row ${!selectedDocId ? 'is-selected' : ''}`}
        onClick={() => {
          setSelectedDocId('')
          setShowDocsPanel(false)
        }}
        title="Search across all indexed documents"
      >
        <div className="doc-item-left">
          <div className="doc-icon-badge all-docs-badge">
            <Layers size={15} />
          </div>
          <div className="doc-item-meta">
            <span className="doc-item-name">All Documents (Entire Library)</span>
            <div className="doc-item-stats">
              <span>Query across all {documents.length} uploaded document{documents.length === 1 ? '' : 's'}</span>
            </div>
          </div>
        </div>
        <div className="doc-item-actions">
          {!selectedDocId ? (
            <span className="scope-active-pill">
              <Check size={11} />
              <span>Active Scope</span>
            </span>
          ) : (
            <button
              type="button"
              className="doc-filter-btn"
              onClick={(e) => {
                e.stopPropagation()
                setSelectedDocId('')
                setShowDocsPanel(false)
              }}
            >
              Select All
            </button>
          )}
        </div>
      </div>

      {documents.length > 0 && (
        <div className="all-docs-section-divider">
          <span>Individual Documents ({documents.length})</span>
        </div>
      )}

      {isDocsLoading && documents.length === 0 ? (
        <div className="docs-empty-state">
          <Loader2 size={20} className="spin-icon" style={{ color: 'var(--accent-blue)' }} />
          <span>Loading indexed documents...</span>
        </div>
      ) : docsError ? (
        <div className="docs-empty-state">
          <AlertCircle size={20} style={{ color: 'var(--accent-red)' }} />
          <span>{docsError}</span>
        </div>
      ) : documents.length === 0 ? (
        <div className="docs-empty-state">
          <FolderOpen size={24} className="docs-empty-icon" />
          <p>No documents uploaded yet.</p>
          <span style={{ fontSize: '11.5px', color: 'var(--text-dim)' }}>
            Attach a PDF below to extract text, compute embeddings, and build the vector index.
          </span>
        </div>
      ) : (
        <div className="docs-list-grid">
          {documents.map(doc => {
            const isFiltered = selectedDocId === doc.id
            const isDeleting = deletingDocId === doc.id
            return (
              <div
                key={doc.id}
                className={`doc-item-card ${isFiltered ? 'is-active-filter' : ''}`}
              >
                <div className="doc-item-left">
                  <div className="doc-icon-badge">
                    <FileText size={16} />
                  </div>
                  <div className="doc-item-meta">
                    <span className="doc-item-name" title={doc.name}>
                      {doc.name}
                    </span>
                    <div className="doc-item-stats">
                      <span>{doc.page_count} pages</span>
                      <span>•</span>
                      <span>{doc.chunk_count} chunks</span>
                      <span>•</span>
                      <span className={`doc-status-badge status-${doc.status || 'ready'}`}>
                        {doc.status === 'ready' && <CheckCircle2 size={10} />}
                        {doc.status === 'processing' && <Loader2 size={10} className="spin-icon" />}
                        {doc.status === 'failed' && <AlertCircle size={10} />}
                        <span>{doc.status || 'ready'}</span>
                      </span>
                    </div>
                  </div>
                </div>

                <div className="doc-item-actions">
                  <button
                    type="button"
                    className={`doc-filter-btn ${isFiltered ? 'active' : ''}`}
                    onClick={() => {
                      setSelectedDocId(isFiltered ? '' : doc.id)
                      if (!isFiltered) setShowDocsPanel(false)
                    }}
                    title={isFiltered ? 'Clear document filter' : 'Filter queries to this document only'}
                  >
                    {isFiltered ? 'Filtering' : 'Filter to doc'}
                  </button>

                  <button
                    type="button"
                    className="doc-delete-btn"
                    onClick={(e) => handleDeleteDocument(doc.id, e)}
                    disabled={isDeleting}
                    title="Delete document and remove its chunks from vector database"
                  >
                    {isDeleting ? (
                      <Loader2 size={14} className="spin-icon" />
                    ) : (
                      <Trash2 size={14} />
                    )}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  </>
  )

  const renderSearchInputCard = ({ isBottomDock = false } = {}) => (
    <div className="search-card-glow-wrapper">
      {isGlowActive && (
        <div
          key={glowKey}
          className="marvo-search-trace-track"
          onAnimationEnd={() => setIsGlowActive(false)}
        >
          <div className="marvo-trace-line">
            <div className="marvo-trace-conic" />
          </div>
        </div>
      )}

      <section
        className={`search-card-container ${isGlowActive ? 'trace-active' : ''}`}
        onClick={triggerAiGlow}
        onDragOver={(e) => {
          e.preventDefault()
          e.stopPropagation()
        }}
        onDrop={(e) => {
          e.preventDefault()
          e.stopPropagation()
          if (!isAuthenticated || !token) {
            openLoginModal("Sign in with Google to upload and search your private documents.")
            return
          }
          if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            const filesArray = Array.from(e.dataTransfer.files)
            const pdfFiles = filesArray.filter(
              file => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
            )
            const rejectedCount = filesArray.length - pdfFiles.length

            if (rejectedCount > 0) {
              setFileError(
                `Only PDF files are supported (${rejectedCount} non-PDF file${rejectedCount > 1 ? 's were' : ' was'} skipped).`
              )
              setTimeout(() => setFileError(''), 4500)
            } else {
              setFileError('')
            }

            pdfFiles.forEach(f => uploadFile(f))
          }
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          multiple
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />

        {fileError && (
          <div className="pdf-error-notice" onClick={(e) => e.stopPropagation()}>
            <AlertCircle size={14} />
            <span>{fileError}</span>
          </div>
        )}

        {/* Real-time Upload Status Chips */}
        {uploads.length > 0 && (
          <div className="attached-files-row" onClick={(e) => e.stopPropagation()}>
            {uploads.map((upload) => (
              <div
                key={upload.id}
                className={`upload-status-chip is-${upload.status}`}
                title={upload.errorReason || upload.name}
              >
                <div className="attached-file-info">
                  <span className="attached-file-name">{upload.name}</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span className="attached-file-size">{formatFileSize(upload.size)}</span>
                    <span className={`upload-status-pill ${upload.status}`}>
                      {upload.status === 'uploading' && (
                        <>
                          <Loader2 size={10} className="spin-icon" />
                          <span>Uploading</span>
                        </>
                      )}
                      {upload.status === 'processing' && (
                        <>
                          <Loader2 size={10} className="spin-icon" />
                          <span>Processing</span>
                        </>
                      )}
                      {upload.status === 'ready' && (
                        <>
                          <CheckCircle2 size={10} />
                          <span>Ready</span>
                        </>
                      )}
                      {upload.status === 'failed' && (
                        <>
                          <AlertCircle size={10} />
                          <span>Failed</span>
                        </>
                      )}
                    </span>
                  </div>
                  {upload.status === 'failed' && upload.errorReason && (
                    <span className="upload-fail-reason">{upload.errorReason}</span>
                  )}
                </div>
                <button
                  type="button"
                  className="remove-file-btn"
                  onClick={(e) => handleDismissUpload(upload.id, e)}
                  title="Dismiss upload"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        <textarea
          className="search-textarea"
          placeholder={
            isUploadingOrProcessing
              ? 'Document is indexing... Ask AI is paused until processing completes'
              : isBottomDock
                ? activeFilteredDoc
                  ? `Ask follow-up question on "${activeFilteredDoc.name}"...`
                  : 'Ask a follow-up question or search across documents...'
                : activeFilteredDoc
                  ? `Ask a question specifically about "${activeFilteredDoc.name}"...`
                  : 'Ask a question across indexed enterprise documents...'
          }
          value={inputVal}
          onChange={(e) => setInputVal(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={triggerAiGlow}
          rows={isBottomDock ? 2 : 2}
          autoFocus={!isBottomDock}
          disabled={isUploadingOrProcessing}
        />

        <div className="search-actions-bar">
          <div className="search-action-left">
            <button
              className={`pill-btn attach-btn-compact ${uploads.length > 0 ? 'active' : ''}`}
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                if (!isAuthenticated || !token) {
                  openLoginModal("Sign in with Google to upload and search your private documents.")
                  return
                }
                fileInputRef.current?.click()
              }}
              title="Attach PDF document to index"
              aria-label="Attach PDF"
            >
              <Plus size={16} style={{ color: uploads.length > 0 ? 'var(--accent-blue)' : 'currentColor' }} />
            </button>

            <div className="all-docs-scope-wrapper" ref={allDocsRef}>
              <button
                className={`pill-btn all-docs-trigger-btn ${showDocsPanel ? 'active' : ''} ${activeFilteredDoc ? 'is-filtered' : ''}`}
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  setShowDocsPanel(prev => !prev)
                }}
                title="Document Scope & Repository"
              >
                {activeFilteredDoc ? (
                  <>
                    <Filter size={12} style={{ color: 'var(--accent-blue)' }} />
                    <span className="scope-doc-name" title={activeFilteredDoc.name}>
                      {activeFilteredDoc.name}
                    </span>
                    <span
                      className="scope-clear-chip"
                      onClick={(e) => {
                        e.stopPropagation()
                        setSelectedDocId('')
                      }}
                      title="Clear filter, search All Documents"
                    >
                      <X size={11} />
                    </span>
                  </>
                ) : (
                  <>
                    <Layers size={13} style={{ color: 'var(--accent-blue)' }} />
                    <span>All Documents ({documents.length})</span>
                  </>
                )}
                <ChevronDown size={12} className={`scope-chevron ${showDocsPanel ? 'open' : ''}`} />
              </button>

              {showDocsPanel && renderDocumentManagerPanel()}
            </div>
          </div>

          {isGenerating ? (
            <button
              className="ask-submit-btn stop-execution-btn"
              onClick={handleStopExecution}
              type="button"
              title="Stop execution"
            >
              <Square size={11} fill="currentColor" />
              <span>Stop</span>
            </button>
          ) : isUploadingOrProcessing ? (
            <button
              className="ask-submit-btn is-upload-paused"
              disabled={true}
              type="button"
              title="Document is being indexed. Ask AI is paused until ready."
            >
              <Loader2 size={13} className="spin-icon" />
              <span>Processing PDF...</span>
            </button>
          ) : (
            <button
              className="ask-submit-btn"
              onClick={() => handleAskQuestion()}
              disabled={!inputVal.trim()}
              type="button"
            >
              <Sparkles size={15} />
              <span>Ask AI</span>
              <span className="shortcut-kbd">⌘↵</span>
            </button>
          )}
        </div>
      </section>
    </div>
  )

  // -------------------------------------------------------------
  // CLAUDE ASSISTANT TURN RENDERER (BORDERLESS CANVAS, MARKDOWN, CITATIONS)
  // -------------------------------------------------------------
  const renderClaudeAssistantTurn = (msg) => {
    const isAiServiceError =
      msg.error ||
      msg.data?.lead?.toLowerCase().includes('ai service') ||
      msg.data?.lead?.toLowerCase().includes('api key')

    const activeSrcId = activeSources[msg.id]
    const activeSrc = msg.data?.sources?.find(s => String(s.id) === String(activeSrcId))
    const isBookmarked = !!bookmarkedMsgs[msg.id]
    const currentFeedback = messageFeedback[msg.id]
    const isCopied = copiedMsgId === msg.id

    const copyAssistantAnswer = () => {
      if (!msg.data) return
      const textToCopy = stripChunkIdCitations(msg.data.answer || msg.data.lead || '')
      navigator.clipboard.writeText(textToCopy)
      setCopiedMsgId(msg.id)
      setTimeout(() => setCopiedMsgId(null), 2000)
    }

    return (
      <div key={msg.id} className="claude-assistant-message-row">
        <div className="claude-assistant-container">
          {/* Subtle Stats Meta (Enterprise AI logo and text completely removed) */}
          {!msg.isGenerating && msg.data?.stats && (
            <div className="claude-assistant-header" style={{ justifyContent: 'flex-end', marginBottom: '4px' }}>
              <span className="claude-assistant-meta">
                {msg.data.stats.responseTime} • {msg.data.stats.sourcesUsed} source{msg.data.stats.sourcesUsed === 1 ? '' : 's'} verified
              </span>
            </div>
          )}

          {/* 1. Loading State: Three Waving Dots (only while waiting for initial tokens) */}
          {msg.isGenerating && !msg.data?.answer && (
            <div className="chat-waving-dots-container" aria-label="Loading response...">
              <div className="chat-waving-dots">
                <span className="chat-dot dot-1" />
                <span className="chat-dot dot-2" />
                <span className="chat-dot dot-3" />
              </div>
            </div>
          )}

          {/* 2. Error State / Stopped State */}
          {msg.error && !msg.isGenerating && (
            <>
              {msg.data?.answer && (
                <ClaudeMarkdown
                  content={msg.data.answer}
                  isStreaming={false}
                  onCitationClick={(citNum) => {
                    setActiveSources(prev => ({
                      ...prev,
                      [msg.id]: prev[msg.id] === citNum ? null : citNum
                    }))
                  }}
                />
              )}
              <div className="claude-conversational-notice" style={msg.data?.answer ? { marginTop: '12px' } : {}}>
                <div
                  className="claude-notice-text"
                  style={{ color: msg.error === 'Generation stopped by user.' ? 'var(--text-muted)' : '#f87171' }}
                >
                  {msg.error === 'Generation stopped by user.' ? (
                    <Square size={13} fill="currentColor" style={{ display: 'inline', marginRight: '6px', verticalAlign: 'text-bottom' }} />
                  ) : (
                    <AlertCircle size={15} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'text-bottom' }} />
                  )}
                  {msg.error}
                </div>
                <div className="claude-notice-actions">
                  <button
                    type="button"
                    className="claude-ghost-btn"
                    onClick={() => handleAskQuestion(currentQuestion)}
                    disabled={isUploadingOrProcessing}
                  >
                    <RotateCcw size={13} />
                    <span>Retry Question</span>
                  </button>
                </div>
              </div>
            </>
          )}

          {/* 3. Not Found / Unanswerable (Claude-Style Conversational Response) */}
          {!msg.isGenerating && !msg.error && msg.data && !msg.data.answerable && (
            <div className="claude-conversational-notice">
              <p className="claude-notice-text">
                {msg.data.lead || "I was unable to find verified documentation matching this question in the indexed documents."}
              </p>

              <div className="claude-suggestions-box">
                <div className="claude-suggestions-header">
                  <AlertCircle size={13} />
                  <span>{isAiServiceError ? 'Troubleshooting steps:' : 'Suggestions to find the information:'}</span>
                </div>
                <ul className="claude-suggestions-list">
                  {isAiServiceError ? (
                    <>
                      <li>Verify that your API key is valid and has active quota.</li>
                      <li>Wait a moment before retrying if rate limits were reached.</li>
                      <li>Check your server console logs for detailed API status codes.</li>
                    </>
                  ) : (
                    <>
                      <li>Check the spelling of technical terms, error codes, or ARNs.</li>
                      {selectedDocId ? (
                        <li>You are filtering to a single document. Clear the filter to search across the entire library.</li>
                      ) : (
                        <li>Ensure the document containing this procedure has been uploaded and indexed.</li>
                      )}
                      <li>Upload additional reference PDFs using the Attach PDF button.</li>
                    </>
                  )}
                </ul>
              </div>

              <div className="claude-notice-actions">
                <button
                  type="button"
                  className="claude-ghost-btn"
                  onClick={() => {
                    if (!isAuthenticated || !token) {
                      openLoginModal("Sign in with Google to upload and search your private documents.")
                      return
                    }
                    fileInputRef.current?.click()
                  }}
                >
                  <Paperclip size={13} />
                  <span>Attach Reference PDF</span>
                </button>
                {selectedDocId && (
                  <button
                    type="button"
                    className="claude-ghost-btn"
                    onClick={() => {
                      setSelectedDocId('')
                      handleAskQuestion(currentQuestion)
                    }}
                  >
                    <RotateCcw size={13} />
                    <span>Search All Documents</span>
                  </button>
                )}
              </div>
            </div>
          )}

          {/* 4. Verified Grounded Answer or Active Streaming */}
          {((!msg.isGenerating && !msg.error && msg.data && msg.data.answerable) ||
            (msg.isGenerating && msg.data?.answer)) && (
            <>
              {/* Rich Markdown Answer with real-time streaming cursor */}
              <ClaudeMarkdown
                content={msg.data.answer || msg.data.lead}
                isStreaming={msg.isGenerating}
                onCitationClick={(citNum) => {
                  setActiveSources(prev => ({
                    ...prev,
                    [msg.id]: prev[msg.id] === citNum ? null : citNum
                  }))
                }}
              />

              {/* Fallback to keyPoints ONLY if neither answer nor lead was present */}
              {!msg.data.answer && !msg.data.lead && msg.data.keyPoints && msg.data.keyPoints.length > 0 && (
                <ul className="claude-prose-ul">
                  {msg.data.keyPoints.map((kp, idx) => (
                    <li key={idx} className="claude-prose-li">{stripChunkIdCitations(kp)}</li>
                  ))}
                </ul>
              )}

              {/* Sources Pills & Collapsible Drawer (Claude-Style) - only when generation is completed */}
              {!msg.isGenerating && msg.data.sources && msg.data.sources.length > 0 && (
                <div className="claude-sources-section">
                  <div className="claude-sources-top">
                    <span className="claude-sources-title">
                      <FileText size={12} />
                      <span>Verified Sources ({msg.data.sources.length})</span>
                    </span>
                  </div>

                  <div className="claude-sources-pills-row">
                    {msg.data.sources.map((src) => {
                      const isSelected = String(activeSrcId) === String(src.id)
                      return (
                        <button
                          key={src.id}
                          type="button"
                          className={`claude-source-pill ${isSelected ? 'active' : ''}`}
                          onClick={() => {
                            setActiveSources(prev => ({
                              ...prev,
                              [msg.id]: isSelected ? null : src.id
                            }))
                          }}
                          title={`Click to preview excerpt from ${src.source_name}`}
                        >
                          <span className="claude-source-pill-num">[{src.id}]</span>
                          <span className="claude-source-pill-name">{src.source_name}</span>
                          <span className="claude-source-pill-page">
                            {typeof src.page === 'string' && src.page.toLowerCase().startsWith('page')
                              ? src.page
                              : `Page ${src.page}`}
                          </span>
                          <ChevronDown
                            size={11}
                            style={{
                              transform: isSelected ? 'rotate(180deg)' : 'none',
                              transition: 'transform 0.18s ease'
                            }}
                          />
                        </button>
                      )
                    })}
                  </div>

                  {/* Expanded Source Preview Drawer */}
                  {activeSrc && (
                    <div className="claude-source-preview-card">
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
                      <p className="claude-source-preview-snippet">
                        "{activeSrc.snippet}"
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Minimalist Ghost Action Bar at Message Bottom - only when generation is completed */}
              {!msg.isGenerating && (
                <div className="claude-actions-toolbar">
                <button
                  type="button"
                  className="claude-ghost-btn"
                  onClick={copyAssistantAnswer}
                  title="Copy full answer text"
                >
                  {isCopied ? (
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

                <button
                  type="button"
                  className={`claude-ghost-btn ${currentFeedback === 'good' ? 'active' : ''}`}
                  onClick={() =>
                    setMessageFeedback(prev => ({
                      ...prev,
                      [msg.id]: prev[msg.id] === 'good' ? null : 'good'
                    }))
                  }
                  title="Good response"
                >
                  <ThumbsUp size={13} />
                  <span>Good</span>
                </button>

                <button
                  type="button"
                  className={`claude-ghost-btn ${currentFeedback === 'bad' ? 'active' : ''}`}
                  onClick={() =>
                    setMessageFeedback(prev => ({
                      ...prev,
                      [msg.id]: prev[msg.id] === 'bad' ? null : 'bad'
                    }))
                  }
                  title="Not useful"
                >
                  <ThumbsDown size={13} />
                  <span>Bad</span>
                </button>

                <button
                  type="button"
                  className={`claude-ghost-btn ${isBookmarked ? 'active' : ''}`}
                  onClick={() =>
                    setBookmarkedMsgs(prev => ({
                      ...prev,
                      [msg.id]: !prev[msg.id]
                    }))
                  }
                  title={isBookmarked ? 'Bookmarked' : 'Bookmark this answer'}
                >
                  <Bookmark
                    size={13}
                    fill={isBookmarked ? '#3b82f6' : 'none'}
                    color={isBookmarked ? '#3b82f6' : 'currentColor'}
                  />
                  <span>{isBookmarked ? 'Saved' : 'Bookmark'}</span>
                </button>
              </div>
            )}
          </>
        )}
        </div>
      </div>
    )
  }

  // =============================================================
  // MAIN VIEW: CONDITIONAL RENDERING (CLAUDE-STYLE)
  // =============================================================
  if (!hasSearched) {
    // -----------------------------------------------------------
    // MODE 1: INITIAL STATE (SEARCH BAR IN MIDDLE)
    // -----------------------------------------------------------
    return (
      <div className="ask-ai-claude-layout initial-mode">
        <div className="ask-ai-search-wrapper">
          {/* Clean text directly above the search bar in initial mode */}
          <div className="claude-hero-container">
            <h1 className="claude-hero-title">What ,can I help you find <span className=''>?</span></h1>
          </div>

          {/* Centered Search Bar */}
          {renderSearchInputCard({ isBottomDock: false })}
        </div>
      </div>
    )
  }

  // -----------------------------------------------------------
  // MODE 2: ACTIVE CONVERSATION STATE (THREAD ABOVE, SEARCH BAR AT BOTTOM)
  // -----------------------------------------------------------
  return (
    <div className="ask-ai-claude-layout active-mode">
      {/* Scrollable Conversation Stream */}
      <div className="claude-thread-scroll">
        {/* Top Thread Bar */}
        <div className="claude-thread-top-bar">
          <div className="claude-thread-meta">
            <span className="claude-scope-chip">
              <Filter size={11} />
              <span>
                {activeFilteredDoc ? `Filtered: ${activeFilteredDoc.name}` : `All Documents (${documents.length})`}
              </span>
            </span>

          </div>

          <button
            type="button"
            className="pill-btn reset-btn"
            onClick={handleResetSearch}
            title="Start new search and return to centered view"
          >
            <RotateCcw size={13} />
            <span>New Search</span>
          </button>
        </div>

        {/* Conversation Thread Messages (Claude-style Stream) */}
        {threadMessages.length > 0 ? (
          threadMessages.map((msg) => {
            if (msg.role === 'user') {
              return (
                <div key={msg.id} className="claude-user-message-row">
                  <div className="claude-user-bubble">
                    <div className="claude-user-bubble-top">
                      {msg.docScope ? (
                        <span className="claude-user-scope-tag">
                          <Filter size={10} />
                          <span>{msg.docScope}</span>
                        </span>
                      ) : <span />}
                      <button
                        type="button"
                        className="claude-user-copy-btn"
                        onClick={() => {
                          navigator.clipboard.writeText(msg.text)
                          setCopiedMsgId(msg.id)
                          setTimeout(() => setCopiedMsgId(null), 1800)
                        }}
                        title="Copy question text"
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

            return renderClaudeAssistantTurn(msg)
          })
        ) : (
          // Fallback single message if threadMessages was not populated
          <>
            <div className="claude-user-message-row">
              <div className="claude-user-bubble">
                <div className="claude-user-query-text">{currentQuestion}</div>
              </div>
            </div>
            {renderClaudeAssistantTurn({
              id: 'fallback-turn',
              role: 'assistant',
              isGenerating,
              error: searchError,
              data: answerData
            })}
          </>
        )}

        <div ref={threadBottomRef} />
      </div>

      {/* Docked Sticky Bottom Search Bar (Claude-style) */}
      <div className="claude-bottom-dock">
        <div className="claude-dock-inner">
          {renderSearchInputCard({ isBottomDock: true })}
        </div>
      </div>
    </div>
  )
}
