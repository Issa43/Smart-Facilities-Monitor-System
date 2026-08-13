import { useCallback, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { WorkOrder } from '@/types'
import {
  MAINTENANCE_TYPE_LABELS,
  PRIORITY_LABELS,
  PRIORITY_TONE,
  WORK_ORDER_STATUS_LABELS,
  WORK_ORDER_STATUS_TONE,
} from '@/types'
import { formatDate, formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { listAssets, listWorkOrders } from '@/api/operations'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { IconButton } from '@/components/ui/Button/Button'
import { Panel } from '@/components/ui/Panel/Panel'
import { ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { Section, SplitGrid } from '@/components/ui/Display/Display'
import { STATUS_COLORS } from '@/components/charts/chartTheme'
import shared from '@/features/shared/Dashboard.module.css'
import styles from './Calendar.module.css'

/** Sunday-first, matching the working week in Saudi Arabia. */
const WEEKDAYS = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']

const MONTH_YEAR = new Intl.DateTimeFormat('ar-SA-u-ca-gregory-nu-latn', {
  month: 'long',
  year: 'numeric',
})

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

export function MaintenanceCalendarPage() {
  const [monthOffset, setMonthOffset] = useState(0)
  const [selectedDay, setSelectedDay] = useState<Date | null>(null)

  const ordersQuery = useQuery({ queryKey: qk.workOrders.list(), queryFn: () => listWorkOrders() })
  const assetsQuery = useQuery({ queryKey: qk.assets.list(), queryFn: () => listAssets() })

  const assetName = useCallback(
    (id: string) => assetsQuery.data?.find((a) => a.id === id)?.name ?? '—',
    [assetsQuery.data],
  )

  const viewDate = useMemo(() => {
    const date = new Date()
    date.setDate(1)
    date.setMonth(date.getMonth() + monthOffset)
    date.setHours(0, 0, 0, 0)
    return date
  }, [monthOffset])

  /** Leading blanks + the month's days, so the grid always starts on Sunday. */
  const cells = useMemo(() => {
    const firstWeekday = viewDate.getDay()
    const daysInMonth = new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 0).getDate()
    const list: (Date | null)[] = Array.from({ length: firstWeekday }, () => null)
    for (let day = 1; day <= daysInMonth; day++) {
      list.push(new Date(viewDate.getFullYear(), viewDate.getMonth(), day))
    }
    return list
  }, [viewDate])

  const ordersByDay = useMemo(() => {
    const map = new Map<string, WorkOrder[]>()
    for (const order of ordersQuery.data ?? []) {
      const key = new Date(order.scheduledDate).toDateString()
      map.set(key, [...(map.get(key) ?? []), order])
    }
    return map
  }, [ordersQuery.data])

  const today = new Date()
  const monthOrders = (ordersQuery.data ?? []).filter((order) => {
    const date = new Date(order.scheduledDate)
    return date.getFullYear() === viewDate.getFullYear() && date.getMonth() === viewDate.getMonth()
  })

  const selectedOrders = selectedDay ? (ordersByDay.get(selectedDay.toDateString()) ?? []) : []

  const upcoming = (ordersQuery.data ?? [])
    .filter(
      (order) =>
        (order.status === 'open' || order.status === 'in_progress') &&
        new Date(order.scheduledDate).getTime() >= today.getTime() - 86_400_000,
    )
    .sort((a, b) => a.scheduledDate.localeCompare(b.scheduledDate))
    .slice(0, 8)

  if (ordersQuery.isError) return <ErrorState error={ordersQuery.error} />

  return (
    <>
      <PageHeader
        title="تقويم الصيانة"
        description="عرض شهري لأوامر الصيانة المجدولة. اضغط على أي يوم لعرض تفاصيل أوامره."
      />

      <Section>
        <SplitGrid>
          <Panel
            title={MONTH_YEAR.format(viewDate)}
            subtitle={`${formatNumber(monthOrders.length)} أمر صيانة مجدول هذا الشهر`}
            actions={
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <IconButton
                  size="sm"
                  label="الشهر السابق"
                  onClick={() => setMonthOffset((current) => current - 1)}
                >
                  <ChevronRight size={16} />
                </IconButton>
                <button
                  type="button"
                  className={styles.todayBtn}
                  onClick={() => setMonthOffset(0)}
                  disabled={monthOffset === 0}
                >
                  اليوم
                </button>
                <IconButton
                  size="sm"
                  label="الشهر التالي"
                  onClick={() => setMonthOffset((current) => current + 1)}
                >
                  <ChevronLeft size={16} />
                </IconButton>
              </div>
            }
          >
            {ordersQuery.isPending ? (
              <SkeletonLines count={6} />
            ) : (
              <>
                <div className={styles.weekdays}>
                  {WEEKDAYS.map((day) => (
                    <div key={day} className={styles.weekday}>
                      {day}
                    </div>
                  ))}
                </div>

                <div className={styles.grid}>
                  {cells.map((date, index) => {
                    if (!date) return <div key={`blank-${index}`} className={styles.blank} />

                    const dayOrders = ordersByDay.get(date.toDateString()) ?? []
                    const isToday = sameDay(date, today)
                    const isSelected = selectedDay ? sameDay(date, selectedDay) : false

                    return (
                      <button
                        key={date.toISOString()}
                        type="button"
                        className={[
                          styles.day,
                          isToday ? styles.today : '',
                          isSelected ? styles.selected : '',
                          dayOrders.length > 0 ? styles.hasEvents : '',
                        ]
                          .filter(Boolean)
                          .join(' ')}
                        onClick={() => setSelectedDay(date)}
                        aria-label={`${formatDate(date)} — ${dayOrders.length} أمر صيانة`}
                      >
                        <span className={styles.dayNumber}>{date.getDate()}</span>
                        {dayOrders.length > 0 && (
                          <span className={styles.dots}>
                            {dayOrders.slice(0, 3).map((order) => (
                              <span
                                key={order.id}
                                className={styles.dot}
                                style={{
                                  background: STATUS_COLORS[WORK_ORDER_STATUS_TONE[order.status]],
                                }}
                              />
                            ))}
                            {dayOrders.length > 3 && (
                              <span className={styles.more}>+{dayOrders.length - 3}</span>
                            )}
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>

                <div className={styles.legend}>
                  {(['open', 'in_progress', 'completed', 'cancelled'] as const).map((status) => (
                    <span key={status} className={styles.legendItem}>
                      <span
                        className={styles.dot}
                        style={{ background: STATUS_COLORS[WORK_ORDER_STATUS_TONE[status]] }}
                      />
                      {WORK_ORDER_STATUS_LABELS[status]}
                    </span>
                  ))}
                </div>
              </>
            )}
          </Panel>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <Panel
              title={selectedDay ? formatDate(selectedDay) : 'اختر يوماً'}
              subtitle={
                selectedDay
                  ? `${formatNumber(selectedOrders.length)} أمر صيانة`
                  : 'اضغط على أي يوم في التقويم'
              }
            >
              {!selectedDay ? (
                <p className={shared.hint}>
                  اختر يوماً من التقويم لعرض أوامر الصيانة المجدولة فيه.
                </p>
              ) : selectedOrders.length === 0 ? (
                <StateCard
                  bare
                  title="لا توجد أوامر"
                  description="لا توجد صيانة مجدولة في هذا اليوم."
                />
              ) : (
                <div className={shared.attentionList}>
                  {selectedOrders.map((order) => (
                    <Link
                      key={order.id}
                      to={`/operations/work-orders/${order.id}`}
                      className={shared.attentionRow}
                    >
                      <span
                        className={shared.attentionBar}
                        style={{ background: STATUS_COLORS[WORK_ORDER_STATUS_TONE[order.status]] }}
                      />
                      <span style={{ flex: 1, minWidth: 0 }}>
                        <span className={shared.attentionTitle}>{order.reason}</span>
                        <span className={shared.attentionMeta}>
                          {assetName(order.assetId)} ·{' '}
                          {MAINTENANCE_TYPE_LABELS[order.maintenanceType]}
                        </span>
                      </span>
                      <Badge tone={PRIORITY_TONE[order.priority]}>
                        {PRIORITY_LABELS[order.priority]}
                      </Badge>
                    </Link>
                  ))}
                </div>
              )}
            </Panel>

            <Panel title="الصيانة القادمة" subtitle="أقرب الأوامر المفتوحة">
              {ordersQuery.isPending ? (
                <SkeletonLines count={4} />
              ) : upcoming.length === 0 ? (
                <StateCard bare title="لا توجد صيانة قادمة" />
              ) : (
                <div className={shared.attentionList}>
                  {upcoming.map((order) => (
                    <Link
                      key={order.id}
                      to={`/operations/work-orders/${order.id}`}
                      className={shared.attentionRow}
                    >
                      <span style={{ flex: 1, minWidth: 0 }}>
                        <span className={shared.attentionTitle}>{order.reason}</span>
                        <span className={shared.attentionMeta}>
                          {formatDate(order.scheduledDate)} · {assetName(order.assetId)}
                        </span>
                      </span>
                    </Link>
                  ))}
                </div>
              )}
            </Panel>
          </div>
        </SplitGrid>
      </Section>
    </>
  )
}
