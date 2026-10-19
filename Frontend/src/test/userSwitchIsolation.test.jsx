import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useState } from 'react'
import AskAI from '../pages/AskAI'
import { AuthContext } from '../context/AuthContext'
import { ChatContext } from '../context/ChatContext'

describe('Multi-tenant UI State Isolation on User Switch', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('resets uploads, selectedDocId, and clears User A document names when switching to User B (with parent key)', async () => {
    const userA = { id: 'user_a', name: 'User Alpha', email: 'alpha@example.com' }
    const userB = { id: 'user_b', name: 'User Beta', email: 'beta@example.com' }

    // Mock fetch for both users
    global.fetch = vi.fn().mockImplementation((url, options) => {
      const urlStr = String(url)
      const authHeader = options?.headers?.Authorization || ''

      // Documents listing
      if (urlStr.includes('/api/documents') && (!options?.method || options.method === 'GET')) {
        if (authHeader.includes('token_a')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => [
              {
                id: 'doc_a_initial',
                name: 'user_a_confidential_q3.pdf',
                page_count: 5,
                chunk_count: 12,
                status: 'ready',
                user_id: 'user_a'
              }
            ]
          })
        }
        if (authHeader.includes('token_b')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => [
              {
                id: 'doc_b_initial',
                name: 'user_b_handbook.pdf',
                page_count: 2,
                chunk_count: 4,
                status: 'ready',
                user_id: 'user_b'
              }
            ]
          })
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => [] })
      }

      // Upload endpoint
      if (urlStr.includes('/api/documents/upload') && options?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          status: 201,
          json: async () => ({
            status: 'processing',
            document_id: 'doc_a_new_uploaded',
            file_name: 'user_a_secret_specs.pdf'
          })
        })
      }

      // Default mock fallback
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) })
    })

    // Test harness that switches between User A and User B
    let switchUserToB
    function TestContainer() {
      const [currentUser, setCurrentUser] = useState(userA)
      const [currentToken, setCurrentToken] = useState('token_a')

      switchUserToB = () => {
        act(() => {
          setCurrentUser(userB)
          setCurrentToken('token_b')
        })
      }

      const authValue = {
        user: currentUser,
        token: currentToken,
        isAuthenticated: true,
        handleUnauthorized: vi.fn(),
        openLoginModal: vi.fn(),
        registerResetHook: vi.fn(() => vi.fn())
      }

      const chatValue = {
        activeChat: null,
        chats: [],
        saveChat: vi.fn(),
        startNewChat: vi.fn(),
        loadChat: vi.fn()
      }

      return (
        <AuthContext.Provider value={authValue}>
          <ChatContext.Provider value={chatValue}>
            {/* key={currentUser?.id ?? 'anon'} matches App.jsx implementation */}
            <AskAI key={currentUser?.id ?? 'anon'} />
          </ChatContext.Provider>
        </AuthContext.Provider>
      )
    }

    const { container } = render(<TestContainer />)

    // Wait for User A's initial documents to load
    await waitFor(() => {
      expect(screen.getByText(/user_a_confidential_q3\.pdf/i)).toBeInTheDocument()
    })

    // 1. Select a document for User A (sets selectedDocId)
    const selectDropdown = container.querySelector('select.pill-btn')
    expect(selectDropdown).toBeInTheDocument()
    fireEvent.change(selectDropdown, { target: { value: 'doc_a_initial' } })
    expect(selectDropdown.value).toBe('doc_a_initial')

    // 2. Perform a file upload as User A (sets uploads state)
    const fileInput = container.querySelector('input[type="file"]')
    expect(fileInput).toBeInTheDocument()

    const secretFile = new File(['secret content'], 'user_a_secret_specs.pdf', {
      type: 'application/pdf'
    })

    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [secretFile] } })
    })

    // Confirm User A's uploaded file chip appears in the document
    await waitFor(() => {
      expect(screen.getByText('user_a_secret_specs.pdf')).toBeInTheDocument()
    })

    // Verify uploads state is populated (upload chip present)
    expect(container.querySelectorAll('.upload-status-chip').length).toBe(1)

    // 3. Switch authenticated user to User B
    switchUserToB()

    // 4. Wait for User B's state to settle
    await waitFor(() => {
      expect(screen.getByText(/user_b_handbook\.pdf/i)).toBeInTheDocument()
    })

    // Assert: uploads is empty (no upload status chips)
    expect(container.querySelectorAll('.upload-status-chip').length).toBe(0)
    expect(container.querySelector('.attached-files-row')).toBeNull()

    // Assert: selectedDocId is ''
    const selectDropdownB = container.querySelector('select.pill-btn')
    expect(selectDropdownB.value).toBe('')

    // Assert: Neither User A's uploaded file nor initial document exists anywhere in the document
    expect(screen.queryByText('user_a_secret_specs.pdf')).not.toBeInTheDocument()
    expect(screen.queryByText(/user_a_confidential_q3\.pdf/i)).not.toBeInTheDocument()
  })

  it('resets internal state via useEffect alone when rendered WITHOUT key prop', async () => {
    const userA = { id: 'user_a', name: 'User Alpha', email: 'alpha@example.com' }
    const userB = { id: 'user_b', name: 'User Beta', email: 'beta@example.com' }

    global.fetch = vi.fn().mockImplementation((url, options) => {
      const urlStr = String(url)
      const authHeader = options?.headers?.Authorization || ''

      if (urlStr.includes('/api/documents') && (!options?.method || options.method === 'GET')) {
        if (authHeader.includes('token_a')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => [
              {
                id: 'doc_a_initial',
                name: 'user_a_doc.pdf',
                page_count: 3,
                chunk_count: 6,
                status: 'ready',
                user_id: 'user_a'
              }
            ]
          })
        }
        if (authHeader.includes('token_b')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => [
              {
                id: 'doc_b_initial',
                name: 'user_b_doc.pdf',
                page_count: 1,
                chunk_count: 2,
                status: 'ready',
                user_id: 'user_b'
              }
            ]
          })
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => [] })
      }

      if (urlStr.includes('/api/documents/upload') && options?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          status: 201,
          json: async () => ({
            status: 'processing',
            document_id: 'doc_a_upload_temp',
            file_name: 'user_a_unkeyed_file.pdf'
          })
        })
      }

      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) })
    })

    let switchUserToB
    function UnkeyedContainer() {
      const [currentUser, setCurrentUser] = useState(userA)
      const [currentToken, setCurrentToken] = useState('token_a')

      switchUserToB = () => {
        act(() => {
          setCurrentUser(userB)
          setCurrentToken('token_b')
        })
      }

      const authValue = {
        user: currentUser,
        token: currentToken,
        isAuthenticated: true,
        handleUnauthorized: vi.fn(),
        openLoginModal: vi.fn(),
        registerResetHook: vi.fn(() => vi.fn())
      }

      const chatValue = {
        activeChat: null,
        chats: [],
        saveChat: vi.fn(),
        startNewChat: vi.fn(),
        loadChat: vi.fn()
      }

      return (
        <AuthContext.Provider value={authValue}>
          <ChatContext.Provider value={chatValue}>
            {/* Intentionally rendered WITHOUT key to test internal useEffect reset */}
            <AskAI />
          </ChatContext.Provider>
        </AuthContext.Provider>
      )
    }

    const { container } = render(<UnkeyedContainer />)

    await waitFor(() => {
      expect(screen.getByText(/user_a_doc\.pdf/i)).toBeInTheDocument()
    })

    const selectDropdown = container.querySelector('select.pill-btn')
    fireEvent.change(selectDropdown, { target: { value: 'doc_a_initial' } })
    expect(selectDropdown.value).toBe('doc_a_initial')

    const fileInput = container.querySelector('input[type="file"]')
    const secretFile = new File(['data'], 'user_a_unkeyed_file.pdf', { type: 'application/pdf' })

    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [secretFile] } })
    })

    await waitFor(() => {
      expect(screen.getByText('user_a_unkeyed_file.pdf')).toBeInTheDocument()
    })

    // Switch to User B
    switchUserToB()

    // Wait for User B document
    await waitFor(() => {
      expect(screen.getByText(/user_b_doc\.pdf/i)).toBeInTheDocument()
    })

    // Verify uploads is empty
    expect(container.querySelectorAll('.upload-status-chip').length).toBe(0)

    // Verify selectedDocId is reset to ''
    const selectDropdownB = container.querySelector('select.pill-btn')
    expect(selectDropdownB.value).toBe('')

    // User A document names are absent
    expect(screen.queryByText('user_a_unkeyed_file.pdf')).not.toBeInTheDocument()
    expect(screen.queryByText(/user_a_doc\.pdf/i)).not.toBeInTheDocument()
  })
})
