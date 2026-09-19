import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { User } from '@/types'
import * as authApi from '@/api/auth'
import { onUnauthorized } from '@/api/client'

interface AuthContextValue {
  user: User | null
  isAuthenticated: boolean
  isInitializing: boolean
  login: (email: string, password: string) => Promise<User>
  logout: () => Promise<void>
  refreshUser: () => Promise<User | null>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isInitializing, setIsInitializing] = useState(true)

  useEffect(() => onUnauthorized(() => setUser(null)), [])

  useEffect(() => {
    let active = true
    authApi
      .restoreSession()
      .then((restored) => {
        if (active) setUser(restored)
      })
      .finally(() => {
        if (active) setIsInitializing(false)
      })
    return () => {
      active = false
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const signedIn = await authApi.login(email, password)
    setUser(signedIn)
    return signedIn
  }, [])

  const logout = useCallback(async () => {
    setUser(null)
    await authApi.logout()
  }, [])

  useEffect(() => {
    if (!user) return
    let disposed = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const events = ['mousedown', 'keydown', 'touchstart', 'scroll'] as const
    const removeListeners = () =>
      events.forEach((event) => window.removeEventListener(event, reset))
    const reset = () => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => void logout(), timeoutMs)
    }
    let timeoutMs = 30 * 60 * 1000

    authApi
      .getEffectiveSettings()
      .then((settings) => {
        if (disposed || !settings.session_timeout_enabled) return
        timeoutMs = Math.max(1, settings.session_timeout_minutes) * 60 * 1000
        events.forEach((event) => window.addEventListener(event, reset, { passive: true }))
        reset()
      })
      .catch(() => {
        // JWT expiry remains the server-enforced fallback if policy retrieval fails.
      })

    return () => {
      disposed = true
      if (timer) clearTimeout(timer)
      removeListeners()
    }
  }, [user, logout])

  const refreshUser = useCallback(async () => {
    try {
      const current = await authApi.getCurrentUser()
      setUser(current)
      return current
    } catch {
      setUser(null)
      return null
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ user, isAuthenticated: user !== null, isInitializing, login, logout, refreshUser }),
    [user, isInitializing, login, logout, refreshUser],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}

export function useAuth(): AuthContextValue {
  const context = use(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}

export function useCurrentUser(): User {
  const { user } = useAuth()
  if (!user) throw new Error('useCurrentUser called outside a protected route')
  return user
}
