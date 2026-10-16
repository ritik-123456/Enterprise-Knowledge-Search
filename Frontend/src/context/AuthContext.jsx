import { createContext, useContext, useState, useEffect, useCallback } from 'react'

const AuthContext = createContext(null)

const API_BASE = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || 'http://localhost:8000'
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || ''

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const saved = localStorage.getItem('eks_auth_user')
      return saved ? JSON.parse(saved) : null
    } catch {
      return null
    }
  })

  const [token, setToken] = useState(() => {
    return localStorage.getItem('eks_auth_token') || null
  })

  const [isAuthLoading, setIsAuthLoading] = useState(false)
  const [authError, setAuthError] = useState(null)
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false)
  const [configuredClientId, setConfiguredClientId] = useState(GOOGLE_CLIENT_ID)

  // Fetch public config from backend if env not injected
  useEffect(() => {
    if (!configuredClientId) {
      fetch(`${API_BASE}/api/auth/config`)
        .then(res => res.json())
        .then(data => {
          if (data.client_id) {
            setConfiguredClientId(data.client_id)
          }
        })
        .catch(err => {
          console.warn('Could not fetch auth config:', err)
        })
    }
  }, [configuredClientId])

  const loginWithGoogle = useCallback(async (credential) => {
    setIsAuthLoading(true)
    setAuthError(null)

    try {
      const res = await fetch(`${API_BASE}/api/auth/google`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential })
      })

      if (!res.ok) {
        let errDetail = 'Google authentication failed'
        try {
          const errData = await res.json()
          if (errData.detail) errDetail = errData.detail
        } catch {
          // Ignore
        }
        throw new Error(errDetail)
      }

      const data = await res.json()
      if (data.success && data.user) {
        setUser(data.user)
        setToken(data.token)
        localStorage.setItem('eks_auth_user', JSON.stringify(data.user))
        localStorage.setItem('eks_auth_token', data.token)
        setIsLoginModalOpen(false)
        return data.user
      } else {
        throw new Error(data.message || 'Authentication unsuccessful')
      }
    } catch (err) {
      console.error('Login error:', err)
      setAuthError(err.message || 'Failed to sign in with Google.')
      throw err
    } finally {
      setIsAuthLoading(false)
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/api/auth/logout`, { method: 'POST' }).catch(() => {})
    } finally {
      setUser(null)
      setToken(null)
      localStorage.removeItem('eks_auth_user')
      localStorage.removeItem('eks_auth_token')
      if (window.google?.accounts?.id) {
        try {
          window.google.accounts.id.disableAutoSelect()
        } catch {
          // Ignore
        }
      }
    }
  }, [])

  // Helper to initialize and render Google button in any container
  const renderGoogleButton = useCallback((containerElement, customOptions = {}) => {
    if (!containerElement || !configuredClientId) return

    const initButton = () => {
      if (window.google?.accounts?.id) {
        window.google.accounts.id.initialize({
          client_id: configuredClientId,
          callback: (response) => {
            if (response.credential) {
              loginWithGoogle(response.credential).catch(() => {})
            }
          },
          auto_select: false
        })

        window.google.accounts.id.renderButton(containerElement, {
          theme: 'filled_black',
          size: 'large',
          shape: 'pill',
          text: 'signin_with',
          logo_alignment: 'left',
          width: 280,
          ...customOptions
        })
      }
    }

    if (window.google?.accounts?.id) {
      initButton()
    } else {
      const checkGsi = setInterval(() => {
        if (window.google?.accounts?.id) {
          clearInterval(checkGsi)
          initButton()
        }
      }, 100)
      setTimeout(() => clearInterval(checkGsi), 5000)
    }
  }, [configuredClientId, loginWithGoogle])

  const value = {
    user,
    token,
    isAuthenticated: Boolean(user && token),
    isAuthLoading,
    authError,
    setAuthError,
    loginWithGoogle,
    logout,
    renderGoogleButton,
    isLoginModalOpen,
    setIsLoginModalOpen,
    clientId: configuredClientId
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
