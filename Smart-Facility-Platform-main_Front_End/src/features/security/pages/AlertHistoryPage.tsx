import { useCallback, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import type { AlertStatus, SecurityAlert } from '@/types'
import {
  ALERT_STATUS_LABELS,
  ALERT_STATUS_TONE,
  ALERT_TYPE_LABELS,
  SEVERITY_LABELS,
  SEVERITY_TONE,
} from '@/types'
import { formatDateTime, formatNumber, formatPercent } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { listAlerts } from '@/api/security'
import { listFacilities } from '@/api/operations'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { ErrorState, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section } from '@/components/ui/Display/Display'
import styles from '@/features/shared/Reports.module.css'

type StatusFilter = AlertStatus | 'all'

const FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'الكل' },
  { value: 'new', label: 'جديدة' },
  { value: 'acknowledged', label: 'تمت المراجعة' },
  { value: 'escalated', label: 'تم التصعيد' },
  { value: 'dismissed', label: 'إنذار كاذب' },
]

const RANGES = [
  { value: 7, label: 'آخر 7 أيام' },
  { value: 30, label: 'آخر 30 يوماً' },
  { value: 90, label: 'آخر 90 يوماً' },
  { value: 0, label: 'كل الفترات' },
] as const

export function AlertHistoryPage() {
  const navigate = useNavigate()
  const [rangeDays, setRangeDays] = useState<number>(30)

  const alertsQuery = useQuery({ queryKey: qk.alerts.list, queryFn: listAlerts })
  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })

  const facilityName = useCallback(
    (id: string) => facilitiesQuery.data?.find((f) => f.id === id)?.name ?? '—',
    [facilitiesQuery.data],
  )

  const cutoff = rangeDays === 0 ? 0 : Date.now() - rangeDays * 86_400_000
  const inRange = (alertsQuery.data ?? []).filter(
    (alert) => new Date(alert.detectedAt).getTime() >= cutoff,
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<
    SecurityAlert,
    StatusFilter
  >(inRange, {
    searchText: useCallback((a: SecurityAlert) => `${a.reference} ${a.location} ${a.source}`, []),
    matchesFilter: useCallback((a: SecurityAlert, v: StatusFilter) => a.status === v, []),
    allValue: 'all',
  })

  const counts = FILTERS.map((option) => ({
    ...option,
    count:
      option.value === 'all'
        ? inRange.length
        : inRange.filter((alert) => alert.status === option.value).length,
  }))

  const dismissed = inRange.filter((alert) => alert.status === 'dismissed').length
  const falseAlarmRate = inRange.length === 0 ? 0 : Math.round((dismissed / inRange.length) * 100)

  if (alertsQuery.isError) return <ErrorState error={alertsQuery.error} />

  return (
    <>
      <PageHeader
        title="سجل التنبيهات"
        description="الأرشيف الكامل للتنبيهات الواردة من نظام المراقبة، مع نتيجة معالجة كل تنبيه."
        actions={
          <label className={styles.periodPicker}>
            <span className={styles.periodLabel}>الفترة</span>
            <select
              value={rangeDays}
              onChange={(event) => setRangeDays(Number(event.target.value))}
            >
              {RANGES.map((range) => (
                <option key={range.value} value={range.value}>
                  {range.label}
                </option>
              ))}
            </select>
          </label>
        }
      />

      <Section>
        <KpiGrid cols={4}>
          <KpiCard
            label="تنبيهات الفترة"
            value={formatNumber(inRange.length)}
            icon="eventLog"
            tone="primary"
            loading={alertsQuery.isPending}
          />
          <KpiCard
            label="تم تصعيدها"
            value={formatNumber(inRange.filter((a) => a.status === 'escalated').length)}
            icon="incidents"
            tone="warning"
            loading={alertsQuery.isPending}
            footnote="تحوّلت إلى حوادث موثّقة"
          />
          <KpiCard
            label="إنذارات كاذبة"
            value={formatNumber(dismissed)}
            icon="response"
            tone="neutral"
            loading={alertsQuery.isPending}
          />
          <KpiCard
            label="معدل الإنذارات الكاذبة"
            value={formatPercent(falseAlarmRate)}
            icon="analytics"
            tone={falseAlarmRate > 30 ? 'warning' : 'success'}
            loading={alertsQuery.isPending}
            progress={falseAlarmRate}
          />
        </KpiGrid>
      </Section>

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder="ابحث برقم التنبيه أو الموقع…"
          />
          <FilterBar
            options={counts}
            value={filter}
            onChange={setFilter}
            label="تصفية السجل حسب الحالة"
          />
        </div>
      </Toolbar>

      <DataTable
        loading={alertsQuery.isPending}
        rows={filtered}
        rowKey={(alert) => alert.id}
        onRowClick={(alert) => navigate(`/security/alerts/${alert.id}`)}
        columns={[
          {
            key: 'ref',
            header: 'رقم التنبيه',
            sortValue: (a) => a.reference,
            render: (a) => <span className="mono">{a.reference}</span>,
          },
          {
            key: 'type',
            header: 'النوع',
            sortValue: (a) => a.type,
            render: (a) => ALERT_TYPE_LABELS[a.type],
          },
          {
            key: 'location',
            header: 'الموقع',
            render: (a) => (
              <div>
                <div>{a.location}</div>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>
                  {facilityName(a.facilityId)}
                </div>
              </div>
            ),
          },
          { key: 'source', header: 'المصدر', render: (a) => a.source },
          {
            key: 'severity',
            header: 'الخطورة',
            sortValue: (a) => a.severity,
            render: (a) => (
              <Badge tone={SEVERITY_TONE[a.severity]}>{SEVERITY_LABELS[a.severity]}</Badge>
            ),
          },
          {
            key: 'detected',
            header: 'وقت الرصد',
            sortValue: (a) => a.detectedAt,
            render: (a) => formatDateTime(a.detectedAt),
          },
          {
            key: 'status',
            header: 'الحالة',
            sortValue: (a) => a.status,
            render: (a) => (
              <Badge tone={ALERT_STATUS_TONE[a.status]}>{ALERT_STATUS_LABELS[a.status]}</Badge>
            ),
          },
        ]}
        empty={
          <StateCard
            bare
            title="لا توجد تنبيهات في هذه الفترة"
            description="جرّب توسيع النطاق الزمني أو تعديل عوامل التصفية."
          />
        }
      />
    </>
  )
}
