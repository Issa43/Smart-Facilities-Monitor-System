import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Square } from 'lucide-react'
import {
  ALERT_TYPE_LABELS,
  INCIDENT_STATUS_LABELS,
  INCIDENT_STATUS_TONE,
  SEVERITY_LABELS,
  SEVERITY_TONE,
} from '@/types'
import { formatNumber, formatPercent, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { getSecurityStats } from '@/api/stats'
import { listIncidents, toggleIncidentAction } from '@/api/security'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Panel } from '@/components/ui/Panel/Panel'
import {
  ErrorState,
  ProgressBar,
  SkeletonLines,
  StateCard,
} from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section } from '@/components/ui/Display/Display'
import { ColumnChart } from '@/components/charts/Charts'
import shared from '@/features/shared/Dashboard.module.css'
import styles from '@/features/operations/pages/WorkOrder.module.css'

/**
 * A single queue of every outstanding response action across all open incidents.
 *
 * The incident pages show actions per incident; this page inverts that so the
 * officer on shift sees one prioritised worklist instead of opening each
 * incident to find what is still pending.
 */
export function ResponseCenterPage() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()

  const statsQuery = useQuery({ queryKey: qk.stats.security, queryFn: getSecurityStats })
  const incidentsQuery = useQuery({ queryKey: qk.incidents.list, queryFn: listIncidents })

  const toggle = useMutation({
    mutationFn: (input: { incidentId: string; actionId: string }) =>
      toggleIncidentAction(input.incidentId, input.actionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.incidents.all })
      showToast({ tone: 'success', title: 'تم تحديث حالة الإجراء' })
    },
  })

  const stats = statsQuery.data
  const openIncidents = (incidentsQuery.data ?? []).filter(
    (incident) => incident.status !== 'closed',
  )

  const allActions = openIncidents.flatMap((incident) =>
    incident.actions.map((action) => ({ incident, action })),
  )
  const pendingActions = allActions.filter((entry) => !entry.action.done)
  const completionRate =
    allActions.length === 0
      ? 100
      : Math.round(((allActions.length - pendingActions.length) / allActions.length) * 100)

  // Critical incidents first — the queue should read top-down as priority order.
  const sortedPending = pendingActions.slice().sort((a, b) => {
    const weight = { critical: 0, high: 1, medium: 2, low: 3 } as const
    return weight[a.incident.severity] - weight[b.incident.severity]
  })

  if (incidentsQuery.isError) return <ErrorState error={incidentsQuery.error} />

  return (
    <>
      <PageHeader
        title="مركز الاستجابة"
        description="قائمة موحّدة بجميع إجراءات الاستجابة المعلّقة عبر الحوادث المفتوحة، مرتّبة حسب درجة الخطورة."
      />

      <Section>
        <KpiGrid cols={4}>
          <KpiCard
            label="حوادث مفتوحة"
            value={formatNumber(openIncidents.length)}
            icon="incidents"
            tone={openIncidents.length > 0 ? 'warning' : 'success'}
            loading={incidentsQuery.isPending}
          />
          <KpiCard
            label="إجراءات معلّقة"
            value={formatNumber(pendingActions.length)}
            icon="response"
            tone={pendingActions.length > 0 ? 'critical' : 'success'}
            loading={incidentsQuery.isPending}
            footnote={pendingActions.length > 0 ? 'تتطلب تنفيذاً' : 'جميع الإجراءات منجزة'}
            footnoteTone={pendingActions.length > 0 ? 'critical' : 'success'}
          />
          <KpiCard
            label="نسبة إنجاز الإجراءات"
            value={formatPercent(completionRate)}
            icon="quality"
            tone={completionRate >= 70 ? 'success' : 'warning'}
            loading={incidentsQuery.isPending}
            progress={completionRate}
          />
          <KpiCard
            label="متوسط زمن الاستجابة"
            value={`${formatNumber(stats?.averageResponseMinutes ?? 0)} دقيقة`}
            icon="progress"
            tone="accent"
            loading={statsQuery.isPending}
          />
        </KpiGrid>
      </Section>

      <Section>
        <Panel title="أداء الاستجابة" subtitle="عدد التنبيهات المُعالَجة شهرياً">
          {statsQuery.isPending ? (
            <SkeletonLines count={5} />
          ) : (
            <ColumnChart
              data={stats?.alertTrend ?? []}
              xKey="label"
              valueKey="value"
              label="تنبيهات مُعالَجة"
              height={220}
            />
          )}
        </Panel>
      </Section>

      <Section>
        <Panel
          title="قائمة الإجراءات المعلّقة"
          subtitle={`${formatNumber(pendingActions.length)} إجراء بانتظار التنفيذ — الأعلى خطورة أولاً`}
        >
          {incidentsQuery.isPending ? (
            <SkeletonLines count={6} />
          ) : sortedPending.length === 0 ? (
            <StateCard
              bare
              title="لا توجد إجراءات معلّقة"
              description="تم تنفيذ جميع إجراءات الاستجابة على الحوادث المفتوحة."
            />
          ) : (
            <ul className={styles.tasks}>
              {sortedPending.map(({ incident, action }) => (
                <li key={`${incident.id}-${action.id}`}>
                  <button
                    type="button"
                    className={styles.task}
                    onClick={() => toggle.mutate({ incidentId: incident.id, actionId: action.id })}
                    disabled={toggle.isPending}
                  >
                    <Square size={17} strokeWidth={2} />
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span style={{ display: 'block', fontWeight: 700 }}>{action.label}</span>
                      <span
                        style={{
                          display: 'block',
                          fontSize: 11.5,
                          color: 'var(--text-muted)',
                          marginTop: 3,
                        }}
                      >
                        {incident.reference} · {ALERT_TYPE_LABELS[incident.type]} ·{' '}
                        {incident.location}
                      </span>
                    </span>
                    <Badge tone={SEVERITY_TONE[incident.severity]}>
                      {SEVERITY_LABELS[incident.severity]}
                    </Badge>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </Section>

      <Section>
        <Panel title="الحوادث المفتوحة ونسبة إنجازها">
          {incidentsQuery.isPending ? (
            <SkeletonLines count={4} />
          ) : openIncidents.length === 0 ? (
            <StateCard bare title="لا توجد حوادث مفتوحة" />
          ) : (
            <div className={shared.metricList}>
              {openIncidents.map((incident) => {
                const done = incident.actions.filter((action) => action.done).length
                const progress =
                  incident.actions.length === 0
                    ? 0
                    : Math.round((done / incident.actions.length) * 100)

                return (
                  <div key={incident.id}>
                    <div className={shared.metricRow} style={{ marginBottom: 7 }}>
                      <Link
                        to={`/security/incidents/${incident.id}`}
                        className={shared.metricLabel}
                        style={{ color: 'var(--text)', fontWeight: 700 }}
                      >
                        {incident.reference} — {ALERT_TYPE_LABELS[incident.type]}
                      </Link>
                      <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <Badge tone={INCIDENT_STATUS_TONE[incident.status]}>
                          {INCIDENT_STATUS_LABELS[incident.status]}
                        </Badge>
                        <span className={shared.metricValue}>
                          {formatNumber(done)}/{formatNumber(incident.actions.length)}
                        </span>
                      </span>
                    </div>
                    <ProgressBar value={progress} size="sm" label={incident.reference} />
                    <div
                      style={{
                        fontSize: 11,
                        color: 'var(--text-faint)',
                        marginTop: 5,
                      }}
                    >
                      {incident.location} · {formatRelative(incident.createdAt)}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Panel>
      </Section>
    </>
  )
}
