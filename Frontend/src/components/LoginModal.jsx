import { useEffect, useRef } from 'react'
import { X, AlertCircle, Lock } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import MarvoLogo from './MarvoLogo'

export default function LoginModal() {
  const {
    isLoginModalOpen,
    setIsLoginModalOpen,
    renderGoogleButton,
    isAuthLoading,
    authError,
    setAuthError
  } = useAuth()
  const { theme } = useTheme()

  const googleBtnRef = useRef(null)

  useEffect(() => {
    if (isLoginModalOpen && googleBtnRef.current) {
      // Clear any previous button contents before rendering
      googleBtnRef.current.innerHTML = ''
      renderGoogleButton(googleBtnRef.current, {
        theme: theme === 'dark' ? 'filled_black' : 'outline',
        size: 'large',
        shape: 'pill',
        width: 300,
        text: 'signin_with'
      })
    }
  }, [isLoginModalOpen, renderGoogleButton, theme])

  if (!isLoginModalOpen) return null

  return (
    <div className="login-modal-overlay" onClick={() => setIsLoginModalOpen(false)}>
      <div className="login-modal-card" onClick={(e) => e.stopPropagation()}>
        {/* Close Button */}
        <button
          className="login-modal-close"
          onClick={() => {
            setAuthError(null)
            setIsLoginModalOpen(false)
          }}
          aria-label="Close login dialog"
        >
          <X size={18} />
        </button>

        {/* Header with App Logo */}
        <div className="login-modal-header">
          <MarvoLogo size={48} className="login-brand-logo" />
          <h2 className="login-modal-title">Sign In to MARVO</h2>
          <p className="login-modal-subtitle">
            Enterprise Knowledge Search & Governance
          </p>
        </div>

        {/* Error Notification */}
        {authError && (
          <div className="login-error-banner">
            <AlertCircle size={16} />
            <span>{authError}</span>
          </div>
        )}

        {/* Google Sign In Button Container */}
        <div className="login-actions-group">
          <div className="google-btn-wrapper">
            <div ref={googleBtnRef} id="google-signin-btn-container" />
          </div>

          {isAuthLoading && (
            <div className="login-loading-indicator">
              <div className="login-spinner" />
              <span>Verifying credentials with Google...</span>
            </div>
          )}
        </div>

        {/* Compliance Footer */}
        <div className="login-modal-footer">
          <div className="login-footer-lock">
            <Lock size={12} />
            <span>End-to-End Enterprise Encryption</span>
          </div>
          <p className="login-terms-text">
            Authorized personnel only. Authentication logs and query telemetry are audited.
          </p>
        </div>
      </div>
    </div>
  )
}
