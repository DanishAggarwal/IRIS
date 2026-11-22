import { useCallback, useEffect, useState } from 'react'
import { getCurrentUser, loginWithGoogle, logout as apiLogout } from '../services/api'
import type { UserProfile } from '../types/api'

export function useAuth() {
  const [user, setUser] = useState<UserProfile | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [authError, setAuthError] = useState<string | null>(null)

  const checkAuth = useCallback(async () => {
    setIsLoading(true)
    try {
      const profile = await getCurrentUser()
      setUser(profile)
      setAuthError(null)
    } catch {
      setUser(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  const login = useCallback(async (idToken: string) => {
    setIsLoading(true)
    setAuthError(null)
    try {
      const profile = await loginWithGoogle(idToken)
      setUser(profile)
      return profile
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Authentication failed. Please try again.'
      setAuthError(message)
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [])

  const logout = useCallback(async () => {
    setIsLoading(true)
    try {
      await apiLogout()
    } finally {
      if (typeof window !== 'undefined' && window.google?.accounts?.id?.disableAutoSelect) {
        window.google.accounts.id.disableAutoSelect()
      }
      setUser(null)
      setIsLoading(false)
    }
  }, [])

  const clearAuthError = useCallback(() => {
    setAuthError(null)
  }, [])

  return {
    user,
    isLoading,
    authError,
    login,
    logout,
    checkAuth,
    clearAuthError,
  }
}
