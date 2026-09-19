import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { cn } from '@/lib/cn'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'
import { NotificationDrawer } from './NotificationDrawer'
import styles from './AppShell.module.css'
import { useSecurityRealtime } from '@/features/security/useSecurityRealtime'

const COLLAPSE_KEY = 'nozom.sidebar.collapsed'

/**
 * The chrome around every signed-in page.
 *
 * Sidebar collapse and drawer visibility live here as plain useState rather
 * than in a context: only Sidebar and Topbar need them, and both are direct
 * children. A context would add indirection for nothing.
 */
export function AppShell() {
  const { pathname } = useLocation()
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === 'true')
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const realtimeState = useSecurityRealtime()

  useEffect(() => {
    localStorage.setItem(COLLAPSE_KEY, String(collapsed))
  }, [collapsed])

  // Any navigation closes the mobile drawer and scrolls back to the top —
  // otherwise a deep-scrolled list leaves the next page opening halfway down.
  useEffect(() => {
    setMobileNavOpen(false)
    window.scrollTo({ top: 0 })
  }, [pathname])

  return (
    <div className={styles.shell}>
      <a href="#main-content" className="skip-link">
        تخطَّ إلى المحتوى الرئيسي
      </a>

      <Sidebar
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed((current) => !current)}
        mobileOpen={mobileNavOpen}
        onCloseMobile={() => setMobileNavOpen(false)}
      />

      {mobileNavOpen && (
        <div className={styles.scrim} onClick={() => setMobileNavOpen(false)} aria-hidden="true" />
      )}

      <div className={styles.main}>
        <Topbar
          onOpenMobileNav={() => setMobileNavOpen(true)}
          onOpenNotifications={() => setNotificationsOpen(true)}
        />

        <main id="main-content" className={cn(styles.content, 'page-enter')} key={pathname}>
          {realtimeState === 'reconnecting' || realtimeState === 'authentication_failed' ? (
            <div className={styles.realtimeNotice} role="status">
              {realtimeState === 'authentication_failed'
                ? 'تعذّر توثيق قناة التنبيهات الفورية. حدّث الجلسة للمتابعة.'
                : 'انقطع التحديث الفوري مؤقتاً؛ تجري إعادة الاتصال وتبقى بيانات REST هي المرجع.'}
            </div>
          ) : null}
          <Outlet />
        </main>
      </div>

      {notificationsOpen && <NotificationDrawer onClose={() => setNotificationsOpen(false)} />}
    </div>
  )
}
