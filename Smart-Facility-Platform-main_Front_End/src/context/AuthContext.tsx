import { createContext, use, useCallback, useMemo, useState, type ReactNode } from 'react'
import type { User } from '@/types'
import * as authApi from '@/api/auth'

interface AuthContextValue {
  user: User | null
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<User>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  // Read synchronously on first render: the router needs to know whether the
  // user is signed in before the first paint, otherwise every refresh flashes
  // the login screen before restoring the session.
  const [user, setUser] = useState<User | null>(() => authApi.getStoredSession())

  const login = useCallback(async (username: string, password: string) => {
    const signedIn = await authApi.login(username, password)
    setUser(signedIn)
    return signedIn
  }, [])

  const logout = useCallback(() => {
    authApi.logout()
    setUser(null)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ user, isAuthenticated: user !== null, login, logout }),
    [user, login, logout],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}

export function useAuth(): AuthContextValue {
  const context = use(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}

/**
 * For the many pages that only render behind a ProtectedRoute and would
 * otherwise need a null check on every field access.
 */
export function useCurrentUser(): User {
  const { user } = useAuth()
  if (!user) throw new Error('useCurrentUser called outside a protected route')
  return user
}
