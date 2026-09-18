import { useDeferredValue, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import type {
  HazardProvider,
  HazardType,
  SafetyAlert,
  SafetyAlertFilters,
  SafetyAlertOrdering,
  SafetyAlertStatus,
  Severity,
} from '@/types'
import {
  HAZARD_PROVIDER_LABELS,
  HAZARD_TYPE_LABELS,
  SAFETY_ACTION_LABELS,
  SAFETY_ALERT_ORDERING_LABELS,
  SAFETY_ALERT_STATUS_LABELS,
  SAFETY_ALERT_STATUS_TONE,
  SAFETY_WORKFLOW_ACTION_LABELS,
  SEVERITY_LABELS,
  SEVERITY_TONE,
} from '@/types'
import { formatDateTime, formatDecimal, formatNumber, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { getSafetyMonitoringCoverage, listSafetyAlerts } from '@/api/safety'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { Field } from '@/components/ui/Field/Field'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { Alert, ErrorState, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiGrid, Section } from '@/components/ui/Display/Display'
import { presentSafetyError } from '../safetyErrors'
import styles from '../Safety.module.css'

type StatusFilter = SafetyAlertStatus | 'all'
type WithdrawnFilter = 'all' | 'yes' | 'no'

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'الكل' },
  ...(Object.keys(SAFETY_ALERT_STATUS_LABELS) as SafetyAlertStatus[]).map((status) => ({
    value: status,
    label: SAFETY_ALERT_STATUS_LABELS[status],
  })),
]

/** Converts a local calendar day from a date input into an ISO boundary. */
function dayBoundary(value: string, edge: 'start' | 'end'): string | undefined {
  if (!value) return undefined
  const date = new Date(`${value}T${edge === 'start' ? '00:00:00' : '23:59:59.999'}`)
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString()
}

export function SafetyAlertsPage({ basePath }: { basePath: '/construction' | '/operations' }) {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [search, setSearchValue] = useState('')
  const [status, setStatusValue] = useState<StatusFilter>('all')
  const [severity, setSeverityValue] = useState<Severity | ''>('')
  const [hazardType, setHazardTypeValue] = useState<HazardType | ''>('')
  const [provider, setProviderValue] = useState<HazardProvider | ''>('')
  const [withdrawn, setWithdrawnValue] = useState<WithdrawnFilter>('all')
  const [ordering, setOrderingValue] = useState<SafetyAlertOrdering>('-created_at')
  const [createdFrom, setCreatedFromValue] = useState('')
  const [createdTo, setCreatedToValue] = useState('')
  const deferredSearch = useDeferredValue(search)

  // Every filter change returns to the first page.
  const update =
    <T,>(setter: (value: T) => void) =>
    (value: T) => {
      setter(value)
      setPage(1)
    }

  const filters: SafetyAlertFilters = {
    page,
    search: deferredSearch || undefined,
    status: status === 'all' ? undefined : status,
    severity: severity || undefined,
    hazardType: hazardType || undefined,
    provider: provider || undefined,
    hazardWithdrawn: withdrawn === 'all' ? undefined : withdrawn === 'yes',
    createdAfter: dayBoundary(createdFrom, 'start'),
    createdBefore: dayBoundary(createdTo, 'end'),
    ordering,
  }
  const hasActiveFilters = Boolean(
    deferredSearch ||
    status !== 'all' ||
    severity ||
    hazardType ||
    provider ||
    withdrawn !== 'all' ||
    createdFrom ||
    createdTo,
  )
  const invalidRange = Boolean(createdFrom && createdTo && createdFrom > createdTo)

  const alertsQuery = useQuery({
    queryKey: qk.safety.alertList(filters),
    queryFn: () => listSafetyAlerts(filters),
    placeholderData: (previous) => previous,
    enabled: !invalidRange,
  })
  const coverageQuery = useQuery({
    queryKey: qk.safety.coverage,
    queryFn: getSafetyMonitoringCoverage,
  })

  const header = (
    <PageHeader
      title="الإنذارات والسلامة"
      description="إنذارات السلامة الناتجة عن مخاطر طبيعية خارجية قرب مشاريعك. التوصيات استرشادية، والقرار النهائي للمدير المسؤول."
    />
  )

  if (alertsQuery.isError && !alertsQuery.data) {
    const presentation = presentSafetyError(alertsQuery.error)
    return (
      <>
        {header}
        <Section>
          {presentation.kind === 'forbidden' || presentation.kind === 'not_found' ? (
            <StateCard
              tone="critical"
              title={presentation.title}
              description={presentation.description}
            />
          ) : (
            <ErrorState
              error={new Error(presentation.description)}
              onRetry={() => alertsQuery.refetch()}
            />
          )}
        </Section>
      </>
    )
  }

  const coverage = coverageQuery.data

  return (
    <>
      {header}

      <Section>
        {coverageQuery.isError ? (
          <Alert
            tone="warning"
            title="تعذّر تحميل تغطية المراقبة"
            description="لا يمكن عرض عدد المشاريع المراقبة حالياً. غياب هذه المعلومات لا يعني غياب المخاطر."
          />
        ) : (
          <KpiGrid cols={3}>
            <KpiCard
              label="مشاريع ضمن نطاق المراقبة"
              value={formatNumber(coverage?.monitoredProjects ?? 0)}
              icon="projects"
              tone="primary"
              loading={coverageQuery.isPending}
            />
            <KpiCard
              label="مشاريع يمكن مطابقتها جغرافياً"
              value={formatNumber(coverage?.projectsWithCoordinates ?? 0)}
              icon="facilities"
              tone="info"
              loading={coverageQuery.isPending}
            />
            <KpiCard
              label="مشاريع بلا إحداثيات"
              value={formatNumber(coverage?.projectsMissingCoordinates ?? 0)}
              icon="emergency"
              tone="neutral"
              footnote="لا يمكن مطابقتها جغرافياً مع المخاطر الخارجية"
              loading={coverageQuery.isPending}
            />
          </KpiGrid>
        )}
      </Section>

      {coverage && !coverage.alertCreationEnabled && (
        <Section>
          <Alert
            tone="info"
            title="إنشاء الإنذارات الخارجية غير مفعّل حالياً"
            description="لن تُنشأ إنذارات جديدة من مصادر المخاطر حتى يفعّلها المدير العام. عدم ظهور إنذارات لا يعني عدم وجود مخاطر."
          />
        </Section>
      )}

      {coverage && coverage.projectsMissingCoordinates > 0 && (
        <Section>
          <Alert
            tone="warning"
            title="بعض المشاريع غير قابلة للمطابقة الجغرافية"
            description={`${formatNumber(coverage.projectsMissingCoordinates)} من المشاريع المراقبة لا تملك إحداثيات، لذلك لا يمكن ربطها بأي خطر خارجي. غياب الإنذارات عنها لا يعني أنها آمنة.`}
          />
        </Section>
      )}

      <Toolbar>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, width: '100%' }}>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <SearchInput
              value={search}
              onChange={update(setSearchValue)}
              placeholder="ابحث باسم المشروع أو عنوان الحدث…"
            />
            <FilterBar
              options={STATUS_FILTERS}
              value={status}
              onChange={update(setStatusValue)}
              label="تصفية الإنذارات حسب الحالة"
            />
          </div>
          <div className={styles.filters}>
            <Field label="الخطورة">
              {(props) => (
                <select
                  {...props}
                  value={severity}
                  onChange={(event) =>
                    update(setSeverityValue)(event.target.value as Severity | '')
                  }
                >
                  <option value="">كل المستويات</option>
                  {(Object.keys(SEVERITY_LABELS) as Severity[]).map((value) => (
                    <option key={value} value={value}>
                      {SEVERITY_LABELS[value]}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field label="نوع الخطر">
              {(props) => (
                <select
                  {...props}
                  value={hazardType}
                  onChange={(event) =>
                    update(setHazardTypeValue)(event.target.value as HazardType | '')
                  }
                >
                  <option value="">كل الأنواع</option>
                  {(Object.keys(HAZARD_TYPE_LABELS) as HazardType[]).map((value) => (
                    <option key={value} value={value}>
                      {HAZARD_TYPE_LABELS[value]}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field label="المصدر">
              {(props) => (
                <select
                  {...props}
                  value={provider}
                  onChange={(event) =>
                    update(setProviderValue)(event.target.value as HazardProvider | '')
                  }
                >
                  <option value="">كل المصادر</option>
                  {(Object.keys(HAZARD_PROVIDER_LABELS) as HazardProvider[]).map((value) => (
                    <option key={value} value={value}>
                      {HAZARD_PROVIDER_LABELS[value]}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field label="حالة الحدث لدى المصدر">
              {(props) => (
                <select
                  {...props}
                  value={withdrawn}
                  onChange={(event) =>
                    update(setWithdrawnValue)(event.target.value as WithdrawnFilter)
                  }
                >
                  <option value="all">الكل</option>
                  <option value="yes">سحبه المصدر</option>
                  <option value="no">لم يُسحب</option>
                </select>
              )}
            </Field>
            <Field label="من تاريخ الإنشاء">
              {(props) => (
                <input
                  {...props}
                  type="date"
                  value={createdFrom}
                  onChange={(event) => update(setCreatedFromValue)(event.target.value)}
                />
              )}
            </Field>
            <Field
              label="إلى تاريخ الإنشاء"
              error={invalidRange ? 'يجب ألا يسبق تاريخ البداية' : undefined}
            >
              {(props) => (
                <input
                  {...props}
                  type="date"
                  value={createdTo}
                  onChange={(event) => update(setCreatedToValue)(event.target.value)}
                />
              )}
            </Field>
            <Field label="الترتيب">
              {(props) => (
                <select
                  {...props}
                  value={ordering}
                  onChange={(event) =>
                    update(setOrderingValue)(event.target.value as SafetyAlertOrdering)
                  }
                >
                  {(Object.keys(SAFETY_ALERT_ORDERING_LABELS) as SafetyAlertOrdering[]).map(
                    (value) => (
                      <option key={value} value={value}>
                        {SAFETY_ALERT_ORDERING_LABELS[value]}
                      </option>
                    ),
                  )}
                </select>
              )}
            </Field>
          </div>
        </div>
      </Toolbar>

      {alertsQuery.isError && alertsQuery.data && (
        <Section>
          <Alert
            tone="critical"
            title={presentSafetyError(alertsQuery.error).title}
            description="تُعرض آخر نتائج محمّلة؛ قد لا تعكس المرشحات الحالية."
          />
        </Section>
      )}

      <DataTable<SafetyAlert>
        loading={alertsQuery.isPending && !invalidRange}
        rows={invalidRange ? [] : (alertsQuery.data?.items ?? [])}
        rowKey={(alert) => alert.id}
        onRowClick={(alert) => navigate(`${basePath}/safety-alerts/${alert.id}`)}
        columns={[
          {
            key: 'severity',
            header: 'الخطورة',
            render: (alert) => (
              <Badge tone={SEVERITY_TONE[alert.severity]}>
                خطورة {SEVERITY_LABELS[alert.severity]}
              </Badge>
            ),
          },
          {
            key: 'hazard',
            header: 'الخطر',
            render: (alert) => (
              <span className={styles.cellStack}>
                <span className={styles.cellTitle}>{alert.hazardEvent.title}</span>
                <span className={styles.cellMeta}>{HAZARD_TYPE_LABELS[alert.hazardType]}</span>
                {(alert.hazardWithdrawnAt || alert.escalatedAt) && (
                  <span className={styles.flags}>
                    {alert.hazardWithdrawnAt && <Badge tone="neutral">سحبه المصدر</Badge>}
                    {alert.escalatedAt && <Badge tone="warning">تم التصعيد</Badge>}
                  </span>
                )}
              </span>
            ),
          },
          { key: 'project', header: 'المشروع', render: (alert) => alert.project.name },
          {
            key: 'distance',
            header: 'المسافة',
            numeric: true,
            render: (alert) => `${formatDecimal(Number(alert.distanceKm))} كم`,
          },
          {
            key: 'occurred',
            header: 'وقت الحدث',
            render: (alert) => (
              <span title={formatDateTime(alert.hazardEvent.occurredAt)}>
                {formatRelative(alert.hazardEvent.occurredAt)}
              </span>
            ),
          },
          {
            key: 'provider',
            header: 'المصدر',
            render: (alert) => HAZARD_PROVIDER_LABELS[alert.hazardEvent.provider],
          },
          {
            key: 'status',
            header: 'الحالة',
            render: (alert) => (
              <Badge tone={SAFETY_ALERT_STATUS_TONE[alert.status]}>
                {SAFETY_ALERT_STATUS_LABELS[alert.status]}
              </Badge>
            ),
          },
          {
            key: 'recommendation',
            header: 'الإجراء الموصى به',
            render: (alert) => SAFETY_ACTION_LABELS[alert.recommendedAction],
          },
          {
            key: 'actions',
            header: 'الإجراءات المتاحة',
            render: (alert) =>
              alert.availableActions.length
                ? alert.availableActions
                    .map((action) => SAFETY_WORKFLOW_ACTION_LABELS[action])
                    .join('، ')
                : '—',
          },
        ]}
        pagination={
          alertsQuery.data && !invalidRange
            ? {
                page: alertsQuery.data.page,
                totalPages: alertsQuery.data.totalPages,
                totalItems: alertsQuery.data.count,
                onPageChange: setPage,
              }
            : undefined
        }
        empty={
          invalidRange ? (
            <StateCard
              bare
              title="نطاق التاريخ غير صالح"
              description="تاريخ النهاية يسبق تاريخ البداية."
            />
          ) : hasActiveFilters ? (
            <StateCard
              bare
              title="لا توجد إنذارات مطابقة للمرشحات"
              description="جرّب تعديل المرشحات أو كلمة البحث. هذا لا يعني عدم وجود مخاطر."
            />
          ) : (
            <StateCard
              bare
              title="لا توجد إنذارات سلامة ضمن نطاقك حالياً"
              description="لم يُنشئ النظام إنذارات لمشاريعك. غياب الإنذارات لا يعني غياب المخاطر؛ راجع تغطية المراقبة أعلاه."
            />
          )
        }
      />
    </>
  )
}
