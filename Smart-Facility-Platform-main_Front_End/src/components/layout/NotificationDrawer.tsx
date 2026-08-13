import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { X } from 'lucide-react'
import type { Tone } from '@/types'
import { NOTIFICATION_CATEGORY_LABELS } from '@/types'
import { cn } from '@/lib/cn'
import { formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { listNotifications, markAllNotificationsRead, markNotificationRead } from '@/api/users'
import { useCurrentUser } from '@/context/AuthContext'
import { Button } from '@/components/ui/Button/Button'
import { SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import styles from './AppShell.module.css'

const TONE_COLORS: Record<Tone, string> = {
  success: 'var(--success)',
  warning: 'var(--warning)',
  critical: 'var(--critical)',
  info: 'var(--primary)',
  neutral: 'var(--border-strong)',
}

export function NotificationDrawer({ onClose }: { onClose: () => void }) {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: notifications, isPending } = useQuery({
    queryKey: qk.notifications.list(user.role),
    queryFn: () => listNotifications(user.role),
  })

  const markRead = useMutation({
    mutationFn: markNotificationRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.notifications.all }),
  })

  const markAll = useMutation({
    mutationFn: () => markAllNotificationsRead(user.role),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.notifications.all }),
  })

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const sorted = notifications
    ?.slice()
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    .slice(0, 20)

  return (
    <>
      <div className={styles.drawerScrim} onClick={onClose} />
      <aside className={styles.drawer} role="dialog" aria-label="الإشعارات">
        <header className={styles.drawerHead}>
          <h2 className={styles.drawerTitle}>الإشعارات</h2>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Button
              variant="subtle"
              size="sm"
              onClick={() => markAll.mutate()}
              loading={markAll.isPending}
            >
              تعليم الكل كمقروء
            </Button>
            <button type="button" onClick={onClose} aria-label="إغلاق">
              <X size={18} strokeWidth={2.2} />
            </button>
          </div>
        </header>

        <div className={styles.drawerBody}>
          {isPending && <SkeletonLines count={6} />}

          {sorted && sorted.length === 0 && (
            <StateCard bare title="لا توجد إشعارات" description="كل شيء على ما يرام حالياً." />
          )}

          {sorted?.map((notification) => (
            <button
              key={notification.id}
              type="button"
              className={cn(styles.notifRow, !notification.read && styles.notifUnread)}
              onClick={() => {
                if (!notification.read) markRead.mutate(notification.id)
                if (notification.href) {
                  navigate(notification.href)
                  onClose()
                }
              }}
            >
              <span
                className={styles.notifBar}
                style={{ background: TONE_COLORS[notification.tone] }}
                aria-hidden="true"
              />
              <span style={{ flex: 1, minWidth: 0 }}>
                <span className={styles.notifTitle}>{notification.title}</span>
                <span className={styles.notifBody}>{notification.body}</span>
                <span className={styles.notifMeta}>
                  {NOTIFICATION_CATEGORY_LABELS[notification.category]} ·{' '}
                  {formatRelative(notification.createdAt)}
                </span>
              </span>
              {!notification.read && (
                <span className={styles.notifDotSmall} aria-label="غير مقروء" />
              )}
            </button>
          ))}
        </div>
      </aside>
    </>
  )
}
