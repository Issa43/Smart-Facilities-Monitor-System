import type { NavigateFunction } from 'react-router-dom'

/**
 * Follow a reset link the backend produced, without ever taking it apart.
 *
 * The backend returns an absolute URL built from `FRONTEND_PASSWORD_RESET_URL`.
 * React Router navigates within the app and cannot take an absolute URL, so the
 * URL is parsed and its own path is handed to the router verbatim. The uid and
 * token ride along inside `search` untouched: nothing here reads them, and no
 * part of the link is reconstructed.
 *
 * A link pointing somewhere other than this app — a `FRONTEND_PASSWORD_RESET_URL`
 * naming a different host or port — cannot be a client-side route, so it falls
 * back to a full page navigation rather than silently landing on the wrong page.
 */
export function followResetLink(resetUrl: string, navigate: NavigateFunction): void {
  const target = new URL(resetUrl, window.location.origin)
  if (target.origin === window.location.origin) {
    navigate(`${target.pathname}${target.search}${target.hash}`, { replace: true })
    return
  }
  window.location.assign(target.href)
}
