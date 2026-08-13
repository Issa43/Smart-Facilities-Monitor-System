import { useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { MapPin, Radio } from 'lucide-react'
import type { AlertType, SecurityAlert } from '@/types'
import {
  ALERT_STATUS_LABELS,
  ALERT_STATUS_TONE,
  ALERT_TYPE_LABELS,
  SEVERITY_LABELS,
  SEVERITY_TONE,
} from '@/types'
import { formatDateTime, formatNumber, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { listAlerts } from '@/api/security'
import { listFacilities } from '@/api/operations'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section } from '@/components/ui/Display/Display'
import { STATUS_COLORS } from '@/components/charts/chartTheme'
import styles from './Alerts.module.css'

type AlertFilter = AlertType | 'all' | 'new' | 'critical'

const FILTERS: { value: AlertFilter; label: string }[] = [
  { value: 'all', label: 'الكل' },
  { value: 'new', label: 'جديدة' },
  { value: 'critical', label: 'حرجة' },
  { value: 'fire', label: 'حريق' },
  { value: 'smoke', label: 'دخان' },
  { value: 'intrusion', label: 'اقتحام' },
  { value: 'motion', label: 'حركة' },
  { value: 'unauthorized_person', label: 'دخول غير مصرح' },
  { value: 'emergency', label: 'طوارئ' },
]

export function AlertsPage() {
  const alertsQuery = useQuery({ queryKey: qk.alerts.list, queryFn: listAlerts })
  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })

  const facilityName = useCallback(
    (id: string) => facilitiesQuery.data?.find((f) => f.id === id)?.name ?? '—',
    [facilitiesQuery.data],
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<
    SecurityAlert,
    AlertFilter
  >(alertsQuery.data, {
    searchText: useCallback((a: SecurityAlert) => `${a.reference} ${a.location} ${a.source}`, []),
    matchesFilter: useCallback((a: SecurityAlert, value: AlertFilter) => {
      if (value === 'new') return a.status === 'new'
      if (value === 'critical') return a.severity === 'critical'
      return a.type === value
    }, []),
    allValue: 'all',
  })

  const alerts = alertsQuery.data ?? []
  const counts = FILTERS.map((option) => ({
    ...option,
    count:
      option.value === 'all'
        ? alerts.length
        : option.value === 'new'
          ? alerts.filter((a) => a.status === 'new').length
          : option.value === 'critical'
            ? alerts.filter((a) => a.severity === 'critical').length
            : alerts.filter((a) => a.type === option.value).length,
  })).filter((option) => option.count > 0 || option.value === 'all')

  if (alertsQuery.isError) return <ErrorState error={alertsQuery.error} />

  return (
    <>
      <PageHeader
        title="التنبيهات الأمنية الحيّة"
        description="تصل التنبيهات تلقائياً من نظام المراقبة الخارجي. راجع كل تنبيه وقرّر الإجراء المناسب — تجاهله كإنذار كاذب أو تصعيده إلى حادث."
      />

      <Section>
        <KpiGrid cols={4}>
          <KpiCard
            label="إجمالي التنبيهات"
            value={formatNumber(alerts.length)}
            icon="securityAlert"
            tone="primary"
            loading={alertsQuery.isPending}
          />
          <KpiCard
            label="جديدة"
            value={formatNumber(alerts.filter((a) => a.status === 'new').length)}
            icon="notifications"
            tone={alerts.some((a) => a.status === 'new') ? 'warning' : 'success'}
            loading={alertsQuery.isPending}
          />
          <KpiCard
            label="حرجة"
            value={formatNumber(alerts.filter((a) => a.severity === 'critical').length)}
            icon="emergency"
            tone="critical"
            loading={alertsQuery.isPending}
          />
          <KpiCard
            label="تم تصعيدها لحوادث"
            value={formatNumber(alerts.filter((a) => a.status === 'escalated').length)}
            icon="incidents"
            tone="info"
            loading={alertsQuery.isPending}
          />
        </KpiGrid>
      </Section>

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput value={query} onChange={setQuery} placeholder="ابحث بالموقع أو المصدر…" />
          <FilterBar options={counts} value={filter} onChange={setFilter} label="تصفية التنبيهات" />
        </div>
      </Toolbar>

      {alertsQuery.isPending ? (
        <SkeletonLines count={6} />
      ) : filtered.length === 0 ? (
        <StateCard
          title="لا توجد تنبيهات مطابقة"
          description="جرّب تعديل كلمة البحث أو اختيار تصنيف آخر."
        />
      ) : (
        <div className={styles.grid}>
          {filtered.map((alert) => {
            const isLive = alert.status === 'new' && alert.severity === 'critical'
            return (
              <Link
                key={alert.id}
                to={`/security/alerts/${alert.id}`}
                className={isLive ? `${styles.card} ${styles.cardLive}` : styles.card}
              >
                <span
                  className={styles.severityBar}
                  style={{ background: STATUS_COLORS[SEVERITY_TONE[alert.severity]] }}
                />

                <div className={styles.cardBody}>
                  <div className={styles.cardHead}>
                    <h3 className={styles.cardTitle}>{ALERT_TYPE_LABELS[alert.type]}</h3>
                    <Badge tone={SEVERITY_TONE[alert.severity]} live={isLive}>
                      {SEVERITY_LABELS[alert.severity]}
                    </Badge>
                  </div>

                  <p className={styles.cardLocation}>
                    <MapPin size={13} strokeWidth={2} />
                    {alert.location}
                  </p>

                  <p className={styles.cardSource}>
                    <Radio size={13} strokeWidth={2} />
                    {alert.source}
                  </p>

                  <div className={styles.cardFoot}>
                    <span className="mono" style={{ fontSize: 11 }}>
                      {alert.reference}
                    </span>
                    <Badge tone={ALERT_STATUS_TONE[alert.status]}>
                      {ALERT_STATUS_LABELS[alert.status]}
                    </Badge>
                  </div>

                  <div className={styles.cardMeta}>
                    <span title={formatDateTime(alert.detectedAt)}>
                      {formatRelative(alert.detectedAt)}
                    </span>
                    <span>{facilityName(alert.facilityId)}</span>
                  </div>
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </>
  )
}
