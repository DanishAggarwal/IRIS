import React, { useEffect, useRef, useState } from 'react'
import { Sparkles, ShieldCheck, AlertCircle, LogIn, Lock } from 'lucide-react'

interface LoginScreenProps {
  onLogin: (idToken: string) => Promise<unknown>
  authError: string | null
  isLoading: boolean
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string
            callback: (response: { credential: string }) => void
            auto_select?: boolean
          }) => void
          renderButton: (
            parent: HTMLElement,
            options: {
              theme?: string
              size?: string
              text?: string
              shape?: string
              logo_alignment?: string
            },
          ) => void
          prompt: () => void
          disableAutoSelect?: () => void
        }
      }
    }
  }
}

export const LoginScreen: React.FC<LoginScreenProps> = ({
  onLogin,
  authError,
  isLoading,
}) => {
  const googleBtnRef = useRef<HTMLDivElement>(null)
  const isInitializedRef = useRef<boolean>(false)
  const [isScriptReady, setIsScriptReady] = useState<boolean>(
    typeof window !== 'undefined' && !!window.google?.accounts?.id,
  )
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || ''

  // Monitor Google Identity Services script availability
  useEffect(() => {
    if (!googleClientId) return

    if (window.google?.accounts?.id) {
      setIsScriptReady(true)
      return
    }

    let intervalId: number | undefined
    let attempts = 0
    const maxAttempts = 50 // 5 seconds (50 * 100ms)

    const checkGoogleLoaded = () => {
      attempts += 1
      if (window.google?.accounts?.id) {
        setIsScriptReady(true)
        if (intervalId) clearInterval(intervalId)
      } else if (attempts >= maxAttempts) {
        if (intervalId) clearInterval(intervalId)
      }
    }

    // Check script element load event as well
    const scriptEl = document.querySelector<HTMLScriptElement>(
      'script[src*="accounts.google.com/gsi/client"]',
    )
    const handleScriptLoad = () => {
      if (window.google?.accounts?.id) {
        setIsScriptReady(true)
        if (intervalId) clearInterval(intervalId)
      }
    }

    if (scriptEl) {
      scriptEl.addEventListener('load', handleScriptLoad)
    }

    intervalId = window.setInterval(checkGoogleLoaded, 100)

    return () => {
      if (scriptEl) {
        scriptEl.removeEventListener('load', handleScriptLoad)
      }
      if (intervalId) clearInterval(intervalId)
    }
  }, [googleClientId])

  // Initialize and render Google button once script is ready and DOM ref is available
  useEffect(() => {
    if (!isScriptReady || !googleClientId || !googleBtnRef.current) return
    if (!window.google?.accounts?.id) return

    // Prevent duplicate rendering
    if (googleBtnRef.current) {
      googleBtnRef.current.innerHTML = ''
    }

    window.google.accounts.id.initialize({
      client_id: googleClientId,
      auto_select: false,
      callback: (response) => {
        if (response.credential) {
          onLogin(response.credential).catch(() => {})
        }
      },
    })

    window.google.accounts.id.renderButton(googleBtnRef.current, {
      theme: 'filled_blue',
      size: 'large',
      text: 'signin_with',
      shape: 'rectangular',
      logo_alignment: 'left',
    })
    isInitializedRef.current = true
  }, [isScriptReady, googleClientId, onLogin])

  return (
    <div className="iris-login-container">
      <div className="iris-login-card">
        <div className="iris-login-hero">
          <div className="iris-logo-mark iris-login-logo" aria-hidden="true">
            <span className="iris-logo-text">IRIS</span>
            <Sparkles className="iris-sparkle-icon" size={16} />
          </div>

          <h1 className="iris-login-title">Information Retrieval &amp; Intelligence System</h1>
          <p className="iris-login-subtitle">
            Grounded institutional question-answering for Punjab Engineering College
          </p>
        </div>

        {authError && (
          <div className="iris-login-error" role="alert">
            <AlertCircle size={16} className="iris-login-error-icon" />
            <span className="iris-login-error-text">{authError}</span>
          </div>
        )}

        <div className="iris-login-auth-box">
          <div className="iris-login-instructions">
            <ShieldCheck size={18} className="text-blue-600 inline mr-1.5" />
            <span>
              Sign in with your <strong>@pec.edu.in</strong> institutional Google account or an
              authorized administrator email.
            </span>
          </div>

          {/* Official Google GSI Button Container */}
          <div ref={googleBtnRef} className="iris-google-btn-wrapper" />

          {/* Development / Mock Login Option: ONLY rendered in Vite development mode when Client ID is unconfigured */}
          {import.meta.env.DEV && !googleClientId && (
            <div className="iris-dev-login-fallback">
              <div className="iris-dev-login-notice">
                <Lock size={14} className="text-amber-600 inline mr-1" />
                <span>Local development mode (VITE_GOOGLE_CLIENT_ID not configured)</span>
              </div>
              <p className="iris-dev-login-hint">
                Select an account identity to authenticate locally:
              </p>
              <div className="iris-dev-login-buttons">
                <button
                  type="button"
                  disabled={isLoading}
                  onClick={() => onLogin('dev_mock_pec_student')}
                  className="iris-btn-dev-login"
                >
                  <LogIn size={14} />
                  <span>Sign in as PEC Student</span>
                </button>
                <button
                  type="button"
                  disabled={isLoading}
                  onClick={() => onLogin('dev_mock_admin')}
                  className="iris-btn-dev-login iris-btn-dev-admin"
                >
                  <LogIn size={14} />
                  <span>Sign in as Administrator</span>
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="iris-login-footer">
          <p>
            IRIS protects institutional documents and personal data. Unauthorized access attempts
            are logged and restricted.
          </p>
        </div>
      </div>
    </div>
  )
}
