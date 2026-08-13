import { Navigate, useLocation } from 'react-router-dom'
import type { Role } from '@/types'
import { useAuth } from '@/context/AuthContext'
import { ROLE_ROUTES } from './routeConfig'
import { AppShell } from '@/components/layout/AppShell'

/**
 * Guards a role's route branch.
 *
 *  · not signed in            -> /login, remembering where they were headed
 *  · signed in, wrong role    -> their own dashboard, not a 403 dead end
 *  · signed in, correct role  -> the app shell with the page inside it
 */
export function ProtectedRoute({ role }: { role: Role }) {
  const { user } = useAuth()
  const location = useLocation()

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }

  if (user.role !== role) {
    return <Navigate to={ROLE_ROUTES[user.role].homePath} replace />
  }

  return <AppShell />
}

/**
 * Guards pages every signed-in user can reach regardless of role — the profile
 * and help pages, which the topbar menu links to from all four roles.
 */
export function AuthenticatedRoute() {
  const { user } = useAuth()
  const location = useLocation()

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }
  return <AppShell />
}

/** Sends "/" to the signed-in user's dashboard, or to the login page. */
export function HomeRedirect() {
  const { user } = useAuth()
  return <Navigate to={user ? ROLE_ROUTES[user.role].homePath : '/login'} replace />
}
