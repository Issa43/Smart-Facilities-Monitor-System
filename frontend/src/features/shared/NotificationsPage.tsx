import { useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { CheckCheck } from 'lucide-react'
import type { AppNotification, NotificationCategory } from '@/types'
import { NOTIFICATION_CATEGORY_LABELS } from '@/types'
import { formatDateTime, formatNumber, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { listNotifications, markAllNotificationsRead, markNotificationRead } from '@/api/users'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { Panel } from '@/components/ui/Panel/Panel'
import { ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiGrid, Section } from '@/components/ui/Display/Display'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { STATUS_COLORS } from '@/components/charts/chartTheme'
import styles from './Notifications.module.css'

type CategoryFilter = NotificationCategory | 'all' | 'unread'

/** The full notification centre — distinct from the compact topbar drawer. */
export function NotificationsPage() {
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const { showToast } = useToast()

  const notificationsQuery = useQuery({
    queryKey: qk.notifications.list(user.role),
    queryFn: () => listNotifications(user.role),
  })

  const markRead = useMutation({
    mutationFn: markNotificationRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.notifications.all }),
  })

  const markAll = useMutation({
    mutationFn: () => markAllNotificationsRead(user.role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.notifications.all })
      showToast({ tone: 'success', title: 'تم تعليم جميع الإشعارات كمقروءة' })
    },
  })

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<
    AppNotification,
    CategoryFilter
  >(notificationsQuery.data, {
    searchText: useCallback(
      (notification: AppNotification) => `${notification.title} ${notification.body}`,
      [],
    ),
    matchesFilter: useCallback(
      (notification: AppNotification, value: CategoryFilter) =>
        value === 'unread' ? !notification.read : notification.category === value,
      [],
    ),
    allValue: 'all',
  })

  const all = notificationsQuery.data ?? []
  const unreadCount = all.filter((notification) => !notification.read).length

  const filters = [
    { value: 'all' as CategoryFilter, label: 'الكل', count: all.length },
    { value: 'unread' as CategoryFilter, label: 'غير مقروءة', count: unreadCount },
    ...(Object.keys(NOTIFICATION_CATEGORY_LABELS) as NotificationCategory[]).map((category) => ({
      value: category as CategoryFilter,
      label: NOTIFICATION_CATEGORY_LABELS[category],
      count: all.filter((notification) => notification.category === category).length,
    })),
  ].filter((option) => option.count > 0 || option.value === 'all' || option.value === 'unread')

  const sorted = filtered.slice().sort((a, b) => b.createdAt.localeCompare(a.createdAt))

  if (notificationsQuery.isError) return <ErrorState error={notificationsQuery.error} />

  return (
    <>
      <PageHeader
        title="مركز الإشعارات"
        description="جميع الإشعارات الموجّهة لدورك الوظيفي — تنبيهات المخزون، أوامر الصيانة، الحوادث الأمنية، وتحديثات المشاريع."
        actions={
          <Button
            variant="ghost"
            loading={markAll.isPending}
            disabled={unreadCount === 0}
            onClick={() => markAll.mutate()}
          >
            <CheckCheck size={15} strokeWidth={2} />
            تعليم الكل كمقروء
          </Button>
        }
      />

      <Section>
        <KpiGrid cols={3}>
          <KpiCard
            label="إجمالي الإشعارات"
            value={formatNumber(all.length)}
            icon="notifications"
            tone="primary"
            loading={notificationsQuery.isPending}
          />
          <KpiCard
            label="غير مقروءة"
            value={formatNumber(unreadCount)}
            icon="eventLog"
            tone={unreadCount > 0 ? 'warning' : 'success'}
            loading={notificationsQuery.isPending}
            footnote={unreadCount > 0 ? 'بانتظار المراجعة' : 'لا توجد إشعارات غير مقروءة'}
            footnoteTone={unreadCount > 0 ? 'warning' : 'success'}
          />
          <KpiCard
            label="إشعارات حرجة"
            value={formatNumber(all.filter((n) => n.tone === 'critical').length)}
            icon="securityAlert"
            tone="critical"
            loading={notificationsQuery.isPending}
          />
        </KpiGrid>
      </Section>

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput value={query} onChange={setQuery} placeholder="ابحث في الإشعارات…" />
          <FilterBar
            options={filters}
            value={filter}
            onChange={setFilter}
            label="تصفية الإشعارات"
          />
        </div>
      </Toolbar>

      <Panel flush>
        {notificationsQuery.isPending ? (
          <div style={{ padding: 20 }}>
            <SkeletonLines count={7} />
          </div>
        ) : sorted.length === 0 ? (
          <StateCard
            bare
            title="لا توجد إشعارات مطابقة"
            description="جرّب تعديل كلمة البحث أو اختيار تصنيف آخر."
          />
        ) : (
          <ul className={styles.list}>
            {sorted.map((notification) => {
              const row = (
                <>
                  <span
                    className={styles.bar}
                    style={{ background: STATUS_COLORS[notification.tone] }}
                    aria-hidden="true"
                  />
                  <span className={styles.body}>
                    <span className={styles.title}>{notification.title}</span>
                    <span className={styles.text}>{notification.body}</span>
                    <span className={styles.meta}>
                      <Badge tone="neutral" plain>
                        {NOTIFICATION_CATEGORY_LABELS[notification.category]}
                      </Badge>
                      <span title={formatDateTime(notification.createdAt)}>
                        {formatRelative(notification.createdAt)}
                      </span>
                    </span>
                  </span>
                  {!notification.read && (
                    <span className={styles.unreadDot} aria-label="غير مقروء" />
                  )}
                </>
              )

              return (
                <li
                  key={notification.id}
                  className={notification.read ? styles.row : `${styles.row} ${styles.rowUnread}`}
                >
                  {notification.href ? (
                    <Link
                      to={notification.href}
                      className={styles.rowInner}
                      onClick={() => {
                        if (!notification.read) markRead.mutate(notification.id)
                      }}
                    >
                      {row}
                    </Link>
                  ) : (
                    <button
                      type="button"
                      className={styles.rowInner}
                      onClick={() => {
                        if (!notification.read) markRead.mutate(notification.id)
                      }}
                    >
                      {row}
                    </button>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </Panel>
    </>
  )
}
