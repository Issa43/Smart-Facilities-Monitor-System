import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import {
  ALERT_STATUS_LABELS,
  ALERT_STATUS_TONE,
  ALERT_TYPE_LABELS,
  ALERT_TYPE_TONE,
  INCIDENT_STATUS_LABELS,
  INCIDENT_STATUS_TONE,
  SEVERITY_LABELS,
  SEVERITY_TONE,
} from '@/types'
import { formatNumber, formatPercent, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { getSecurityStats } from '@/api/stats'
import { listAlerts, listIncidents } from '@/api/security'
import { listFacilities } from '@/api/operations'
import { PageHeader } from '@/components/layout/PageHeader'
import { Icon } from '@/components/icons'
import { Badge } from '@/components/ui/Badge/Badge'
import { LinkButton } from '@/components/ui/Button/Button'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { Panel } from '@/components/ui/Panel/Panel'
import { ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiGrid, Section } from '@/components/ui/Display/Display'
import { ColumnChart, DonutChart } from '@/components/charts/Charts'
import { STATUS_COLORS } from '@/components/charts/chartTheme'
import shared from '@/features/shared/Dashboard.module.css'

const QUICK_ACTIONS = [
  {
    to: '/security/alerts',
    icon: 'securityAlert',
    label: 'التنبيهات الحيّة',
    hint: 'مراجعة فورية',
  },
  { to: '/security/incidents', icon: 'incidents', label: 'إدارة الحوادث', hint: 'إنشاء ومتابعة' },
  { to: '/security/cameras', icon: 'camera', label: 'مراقبة الكاميرات', hint: 'عرض مباشر' },
  { to: '/security/emergency', icon: 'emergency', label: 'المراقبة الطارئة', hint: 'حالة الطوارئ' },
] as const

export function SecurityDashboardPage() {
  const statsQuery = useQuery({ queryKey: qk.stats.security, queryFn: getSecurityStats })
  const alertsQuery = useQuery({ queryKey: qk.alerts.list, queryFn: listAlerts })
  const incidentsQuery = useQuery({ queryKey: qk.incidents.list, queryFn: listIncidents })
  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })

  const stats = statsQuery.data
  const newAlerts = alertsQuery.data?.filter((alert) => alert.status === 'new') ?? []
  const openIncidents = incidentsQuery.data?.filter((i) => i.status !== 'closed') ?? []
  const facilityName = (id: string) =>
    facilitiesQuery.data?.find((facility) => facility.id === id)?.name ?? '—'

  const critical = newAlerts.filter((alert) => alert.severity === 'critical').length
  const isCalm = critical === 0

  if (statsQuery.isError) return <ErrorState error={statsQuery.error} />

  return (
    <>
      <PageHeader
        title={
          <>
            لوحة التحكم الأمنية
            <span
              className={isCalm ? shared.livePill : `${shared.livePill} ${shared.livePillCritical}`}
            >
              <span className={shared.liveDot} />
              {isCalm ? 'الوضع مستقر' : `${formatNumber(critical)} تنبيه حرج`}
            </span>
          </>
        }
        description="متابعة التنبيهات الواردة من نظام المراقبة، وتوثيق الحوادث، ومتابعة إجراءات الاستجابة حتى الإغلاق."
        actions={
          <>
            <LinkButton to="/security/alerts" variant="ghost">
              التنبيهات الحيّة
            </LinkButton>
            <LinkButton to="/security/incidents">إدارة الحوادث</LinkButton>
          </>
        }
      />

      <Section>
        <KpiGrid>
          <KpiCard
            label="تنبيهات جديدة"
            value={formatNumber(stats?.newAlerts ?? 0)}
            icon="securityAlert"
            tone={(stats?.newAlerts ?? 0) > 0 ? 'warning' : 'success'}
            loading={statsQuery.isPending}
            footnote={
              (stats?.newAlerts ?? 0) > 0 ? 'بانتظار المراجعة' : 'تمت مراجعة جميع التنبيهات'
            }
            footnoteTone={(stats?.newAlerts ?? 0) > 0 ? 'warning' : 'success'}
          />
          <KpiCard
            label="تنبيهات حرجة"
            value={formatNumber(stats?.criticalAlerts ?? 0)}
            icon="emergency"
            tone={(stats?.criticalAlerts ?? 0) > 0 ? 'critical' : 'success'}
            loading={statsQuery.isPending}
            footnote={
              (stats?.criticalAlerts ?? 0) > 0 ? 'تتطلب إجراءً فورياً' : 'لا توجد تنبيهات حرجة'
            }
            footnoteTone={(stats?.criticalAlerts ?? 0) > 0 ? 'critical' : 'success'}
          />
          <KpiCard
            label="تنبيهات آخر 24 ساعة"
            value={formatNumber(stats?.alertsToday ?? 0)}
            icon="eventLog"
            tone="info"
            loading={statsQuery.isPending}
          />
          <KpiCard
            label="معدل الإنذارات الكاذبة"
            value={formatPercent(stats?.falseAlarmRate ?? 0)}
            icon="analytics"
            tone={(stats?.falseAlarmRate ?? 0) > 30 ? 'warning' : 'neutral'}
            loading={statsQuery.isPending}
            progress={stats?.falseAlarmRate ?? 0}
          />
          <KpiCard
            label="حوادث مفتوحة"
            value={formatNumber(stats?.openIncidents ?? 0)}
            icon="incidents"
            tone={(stats?.openIncidents ?? 0) > 0 ? 'warning' : 'success'}
            loading={statsQuery.isPending}
            footnote="قيد التحقيق أو المعالجة"
          />
          <KpiCard
            label="حوادث مغلقة"
            value={formatNumber(stats?.closedIncidents ?? 0)}
            icon="quality"
            tone="success"
            loading={statsQuery.isPending}
            footnote="تمت جميع إجراءاتها"
          />
          <KpiCard
            label="حوادث هذا الشهر"
            value={formatNumber(stats?.incidentsThisMonth ?? 0)}
            icon="response"
            tone="primary"
            loading={statsQuery.isPending}
          />
          <KpiCard
            label="متوسط زمن الاستجابة"
            value={`${formatNumber(stats?.averageResponseMinutes ?? 0)} دقيقة`}
            icon="progress"
            tone="accent"
            loading={statsQuery.isPending}
            footnote="من الإنذار حتى وصول الفريق"
          />
        </KpiGrid>
      </Section>

      <Section>
        <div className={shared.chartRow}>
          <Panel title="اتجاه التنبيهات" subtitle="عدد التنبيهات الواردة شهرياً خلال آخر ستة أشهر">
            {statsQuery.isPending ? (
              <SkeletonLines count={5} />
            ) : (
              <ColumnChart
                data={stats?.alertTrend ?? []}
                xKey="label"
                valueKey="value"
                label="تنبيهات"
              />
            )}
          </Panel>

          <Panel title="التنبيهات حسب النوع">
            {statsQuery.isPending ? (
              <SkeletonLines count={4} />
            ) : (
              <DonutChart
                slices={stats?.alertsByType ?? []}
                centerValue={formatNumber(alertsQuery.data?.length ?? 0)}
                centerLabel="تنبيه"
              />
            )}
          </Panel>
        </div>
      </Section>

      <Section>
        <div className={shared.chartRow}>
          <Panel
            title="التنبيهات الجديدة"
            subtitle="واردة من نظام المراقبة وبانتظار المراجعة"
            actions={
              <Link to="/security/alerts" className={shared.metricLabel}>
                عرض الكل <ArrowLeft size={12} style={{ display: 'inline' }} />
              </Link>
            }
          >
            {alertsQuery.isPending ? (
              <SkeletonLines count={5} />
            ) : newAlerts.length === 0 ? (
              <StateCard
                bare
                title="لا توجد تنبيهات جديدة"
                description="تمت مراجعة جميع التنبيهات الواردة."
              />
            ) : (
              <div className={shared.attentionList}>
                {newAlerts.slice(0, 6).map((alert) => (
                  <Link
                    key={alert.id}
                    to={`/security/alerts/${alert.id}`}
                    className={shared.attentionRow}
                  >
                    <span
                      className={shared.attentionBar}
                      style={{ background: STATUS_COLORS[SEVERITY_TONE[alert.severity]] }}
                    />
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span className={shared.attentionTitle}>{ALERT_TYPE_LABELS[alert.type]}</span>
                      <span className={shared.attentionMeta}>
                        {alert.location} · {formatRelative(alert.detectedAt)}
                      </span>
                    </span>
                    <Badge tone={ALERT_TYPE_TONE[alert.type]} live={alert.severity === 'critical'}>
                      {SEVERITY_LABELS[alert.severity]}
                    </Badge>
                  </Link>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="إجراءات سريعة">
            <div className={shared.quickGrid}>
              {QUICK_ACTIONS.map((action) => (
                <Link key={action.to} to={action.to} className={shared.quickAction}>
                  <span className={shared.quickIcon}>
                    <Icon name={action.icon} size={18} />
                  </span>
                  <span>
                    <span className={shared.quickLabel}>{action.label}</span>
                    <span className={shared.quickHint}>{action.hint}</span>
                  </span>
                </Link>
              ))}
            </div>

            <div style={{ marginTop: 20 }} className={shared.metricList}>
              {stats?.incidentsBySeverity.map((slice) => (
                <div key={slice.label} className={shared.metricRow}>
                  <span className={shared.metricLabel}>
                    <span
                      style={{
                        display: 'inline-block',
                        width: 8,
                        height: 8,
                        borderRadius: 2.5,
                        background: STATUS_COLORS[slice.tone],
                        marginInlineEnd: 7,
                      }}
                    />
                    حوادث {slice.label}
                  </span>
                  <span className={shared.metricValue}>{formatNumber(slice.value)}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </Section>

      <Section>
        <Panel
          title="الحوادث المفتوحة"
          actions={
            <Link to="/security/incidents" className={shared.metricLabel}>
              عرض الكل <ArrowLeft size={12} style={{ display: 'inline' }} />
            </Link>
          }
        >
          {incidentsQuery.isPending ? (
            <SkeletonLines count={4} />
          ) : openIncidents.length === 0 ? (
            <StateCard
              bare
              title="لا توجد حوادث مفتوحة"
              description="تم إغلاق جميع الحوادث المسجّلة."
            />
          ) : (
            <div className={shared.strip}>
              {openIncidents.map((incident) => (
                <Link
                  key={incident.id}
                  to={`/security/incidents/${incident.id}`}
                  className={shared.stripCard}
                >
                  <div className={shared.stripHead}>
                    <div>
                      <span className={shared.stripName}>{ALERT_TYPE_LABELS[incident.type]}</span>
                      <span className={shared.stripMeta}>{facilityName(incident.facilityId)}</span>
                    </div>
                    <Badge tone={INCIDENT_STATUS_TONE[incident.status]}>
                      {INCIDENT_STATUS_LABELS[incident.status]}
                    </Badge>
                  </div>
                  <div className={shared.stripFoot}>
                    <span className="mono">{incident.reference}</span>
                    <Badge tone={SEVERITY_TONE[incident.severity]}>
                      {SEVERITY_LABELS[incident.severity]}
                    </Badge>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </Panel>
      </Section>

      {alertsQuery.data && alertsQuery.data.length > 0 && (
        <Section>
          <Panel title="آخر التنبيهات المُعالَجة" subtitle="تنبيهات تمت مراجعتها أو تصعيدها">
            <div className={shared.attentionList}>
              {alertsQuery.data
                .filter((alert) => alert.status !== 'new')
                .slice(0, 5)
                .map((alert) => (
                  <Link
                    key={alert.id}
                    to={`/security/alerts/${alert.id}`}
                    className={shared.attentionRow}
                  >
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span className={shared.attentionTitle}>
                        {ALERT_TYPE_LABELS[alert.type]} — {alert.location}
                      </span>
                      <span className={shared.attentionMeta}>
                        {alert.source} · {formatRelative(alert.detectedAt)}
                      </span>
                    </span>
                    <Badge tone={ALERT_STATUS_TONE[alert.status]}>
                      {ALERT_STATUS_LABELS[alert.status]}
                    </Badge>
                  </Link>
                ))}
            </div>
          </Panel>
        </Section>
      )}
    </>
  )
}
