import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { formatNumber, formatPercent } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { getSecurityStats } from '@/api/stats'
import { listAlerts, listIncidents } from '@/api/security'
import { listFacilities } from '@/api/operations'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/ui/Panel/Panel'
import { ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section, SplitGrid } from '@/components/ui/Display/Display'
import { ColumnChart, ComparisonBars, DonutChart } from '@/components/charts/Charts'
import shared from '@/features/shared/Dashboard.module.css'
import styles from './Heatmap.module.css'

const WEEKDAYS = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']

export function IncidentAnalyticsPage() {
  const statsQuery = useQuery({ queryKey: qk.stats.security, queryFn: getSecurityStats })
  const alertsQuery = useQuery({ queryKey: qk.alerts.list, queryFn: listAlerts })
  const incidentsQuery = useQuery({ queryKey: qk.incidents.list, queryFn: listIncidents })
  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })

  const stats = statsQuery.data
  const alerts = alertsQuery.data ?? []
  const incidents = incidentsQuery.data ?? []
  const facilities = facilitiesQuery.data ?? []

  /**
   * Facility × weekday counts, plus the max used to scale cell intensity.
   *
   * Depends on the raw query data rather than the `?? []` locals above: those
   * are fresh array literals on every render, which would defeat the memo.
   */
  const heatmap = useMemo(() => {
    const rows = (facilitiesQuery.data ?? []).map((facility) => {
      const counts = WEEKDAYS.map(
        (_, dayIndex) =>
          (alertsQuery.data ?? []).filter(
            (alert) =>
              alert.facilityId === facility.id && new Date(alert.detectedAt).getDay() === dayIndex,
          ).length,
      )
      return { facility, counts }
    })
    const max = Math.max(1, ...rows.flatMap((row) => row.counts))
    return { rows, max }
  }, [alertsQuery.data, facilitiesQuery.data])

  const byFacility = facilities
    .map((facility) => ({
      label: facility.name,
      value: incidents.filter((incident) => incident.facilityId === facility.id).length,
    }))
    .filter((row) => row.value > 0)
    .sort((a, b) => b.value - a.value)

  const closedIncidents = incidents.filter((incident) => incident.closedAt)
  const averageCloseHours =
    closedIncidents.length === 0
      ? 0
      : Math.round(
          closedIncidents.reduce((sum, incident) => {
            const opened = new Date(incident.createdAt).getTime()
            const closed = new Date(incident.closedAt as string).getTime()
            return sum + (closed - opened) / 3_600_000
          }, 0) / closedIncidents.length,
        )

  const resolutionRate =
    incidents.length === 0 ? 0 : Math.round((closedIncidents.length / incidents.length) * 100)

  if (statsQuery.isError) return <ErrorState error={statsQuery.error} />

  return (
    <>
      <PageHeader
        title="تحليلات الحوادث"
        description="أنماط التنبيهات والحوادث عبر الزمن والمواقع — لتحديد أين ومتى تتركّز المخاطر الأمنية."
      />

      <Section>
        <KpiGrid cols={4}>
          <KpiCard
            label="إجمالي الحوادث"
            value={formatNumber(incidents.length)}
            icon="incidents"
            tone="primary"
            loading={incidentsQuery.isPending}
            footnote={`${formatNumber(stats?.incidentsThisMonth ?? 0)} خلال آخر 30 يوماً`}
          />
          <KpiCard
            label="نسبة الإغلاق"
            value={formatPercent(resolutionRate)}
            icon="quality"
            tone={resolutionRate >= 70 ? 'success' : 'warning'}
            loading={incidentsQuery.isPending}
            progress={resolutionRate}
          />
          <KpiCard
            label="متوسط زمن الإغلاق"
            value={averageCloseHours === 0 ? '—' : `${formatNumber(averageCloseHours)} ساعة`}
            icon="progress"
            tone="info"
            loading={incidentsQuery.isPending}
            footnote="من التسجيل حتى الإغلاق"
          />
          <KpiCard
            label="معدل الإنذارات الكاذبة"
            value={formatPercent(stats?.falseAlarmRate ?? 0)}
            icon="analytics"
            tone={(stats?.falseAlarmRate ?? 0) > 30 ? 'warning' : 'neutral'}
            loading={statsQuery.isPending}
            progress={stats?.falseAlarmRate ?? 0}
          />
        </KpiGrid>
      </Section>

      <Section>
        <Panel title="اتجاه التنبيهات الشهري" subtitle="عدد التنبيهات الواردة خلال آخر ستة أشهر">
          {statsQuery.isPending ? (
            <SkeletonLines count={5} />
          ) : (
            <ColumnChart
              data={stats?.alertTrend ?? []}
              xKey="label"
              valueKey="value"
              label="تنبيهات"
              height={250}
            />
          )}
        </Panel>
      </Section>

      <Section>
        <SplitGrid even>
          <Panel title="الحوادث حسب درجة الخطورة">
            {statsQuery.isPending ? (
              <SkeletonLines count={4} />
            ) : (
              <DonutChart
                slices={stats?.incidentsBySeverity ?? []}
                centerValue={formatNumber(incidents.length)}
                centerLabel="حادث"
                size={200}
              />
            )}
          </Panel>

          <Panel title="التنبيهات حسب النوع">
            {statsQuery.isPending ? (
              <SkeletonLines count={4} />
            ) : (
              <DonutChart
                slices={stats?.alertsByType ?? []}
                centerValue={formatNumber(alerts.length)}
                centerLabel="تنبيه"
                size={200}
              />
            )}
          </Panel>
        </SplitGrid>
      </Section>

      <Section>
        <Panel
          title="خريطة حرارية — التنبيهات حسب المنشأة ويوم الأسبوع"
          subtitle="كلما اشتدّ لون الخلية زاد عدد التنبيهات المسجّلة في ذلك اليوم"
        >
          {alertsQuery.isPending ? (
            <SkeletonLines count={5} />
          ) : heatmap.rows.length === 0 ? (
            <StateCard bare title="لا توجد بيانات كافية" />
          ) : (
            <div className={styles.scroll}>
              <table className={styles.heatmap}>
                <thead>
                  <tr>
                    <th className={styles.corner}>المنشأة</th>
                    {WEEKDAYS.map((day) => (
                      <th key={day}>{day}</th>
                    ))}
                    <th>الإجمالي</th>
                  </tr>
                </thead>
                <tbody>
                  {heatmap.rows.map((row) => {
                    const total = row.counts.reduce((sum, count) => sum + count, 0)
                    return (
                      <tr key={row.facility.id}>
                        <th scope="row" className={styles.rowHead}>
                          {row.facility.name}
                        </th>
                        {row.counts.map((count, index) => (
                          <td key={index}>
                            <span
                              className={styles.cell}
                              style={{
                                // Intensity is a single-hue sequential ramp — the
                                // correct encoding for magnitude.
                                background:
                                  count === 0
                                    ? 'var(--surface-alt)'
                                    : `color-mix(in srgb, var(--primary-dark) ${Math.round((count / heatmap.max) * 85) + 15}%, #ffffff)`,
                                color: count / heatmap.max > 0.5 ? '#fff' : 'var(--text-muted)',
                              }}
                              title={`${row.facility.name} — ${WEEKDAYS[index]}: ${count} تنبيه`}
                            >
                              {count > 0 ? formatNumber(count) : ''}
                            </span>
                          </td>
                        ))}
                        <td className={styles.total}>{formatNumber(total)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>

              <div className={styles.legend}>
                <span className={styles.legendLabel}>أقل</span>
                {[0, 25, 50, 75, 100].map((step) => (
                  <span
                    key={step}
                    className={styles.legendSwatch}
                    style={{
                      background:
                        step === 0
                          ? 'var(--surface-alt)'
                          : `color-mix(in srgb, var(--primary-dark) ${step}%, #ffffff)`,
                    }}
                  />
                ))}
                <span className={styles.legendLabel}>أكثر</span>
              </div>
            </div>
          )}
        </Panel>
      </Section>

      <Section>
        <SplitGrid>
          <Panel title="الحوادث حسب المنشأة" subtitle="أي منشأة تسجّل أكثر الحوادث">
            {incidentsQuery.isPending ? (
              <SkeletonLines count={5} />
            ) : byFacility.length === 0 ? (
              <StateCard bare title="لا توجد حوادث مسجّلة" />
            ) : (
              <ComparisonBars bars={byFacility} />
            )}
          </Panel>

          <Panel title="الملخص التنفيذي">
            <p className={shared.hint}>
              سُجّل <strong>{formatNumber(incidents.length)}</strong> حادثاً أمنياً، أُغلق منها{' '}
              <strong>{formatNumber(closedIncidents.length)}</strong> بنسبة إغلاق{' '}
              <strong>{formatPercent(resolutionRate)}</strong> ومتوسط زمن إغلاق{' '}
              <strong>{formatNumber(averageCloseHours)}</strong> ساعة.
            </p>
            <p className={shared.hint} style={{ marginTop: 14 }}>
              من إجمالي <strong>{formatNumber(alerts.length)}</strong> تنبيه وارد من نظام المراقبة،
              صُنّف <strong>{formatPercent(stats?.falseAlarmRate ?? 0)}</strong> منها كإنذارات كاذبة
              — وهو مؤشر على الحاجة لمعايرة حساسية بعض الحساسات.
            </p>
            {byFacility[0] && (
              <p className={shared.hint} style={{ marginTop: 14 }}>
                تتصدّر <strong>{byFacility[0].label}</strong> قائمة المنشآت من حيث عدد الحوادث بـ{' '}
                <strong>{formatNumber(byFacility[0].value)}</strong> حادثاً، ويُوصى بمراجعة إجراءات
                التأمين فيها.
              </p>
            )}
          </Panel>
        </SplitGrid>
      </Section>
    </>
  )
}
