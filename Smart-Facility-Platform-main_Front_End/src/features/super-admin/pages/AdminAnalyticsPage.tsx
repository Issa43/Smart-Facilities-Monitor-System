import { useQuery } from '@tanstack/react-query'
import { FACILITY_TYPE_LABELS } from '@/types'
import { formatNumber, formatPercent } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { getAdminStats } from '@/api/stats'
import { listProjects } from '@/api/construction'
import { listFacilities } from '@/api/operations'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/ui/Panel/Panel'
import { ErrorState, SkeletonLines } from '@/components/ui/Feedback/Feedback'
import { KpiGrid, Section, SplitGrid } from '@/components/ui/Display/Display'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { AreaChart, ComparisonBars, DonutChart } from '@/components/charts/Charts'
import shared from '@/features/shared/Dashboard.module.css'

export function AdminAnalyticsPage() {
  const statsQuery = useQuery({ queryKey: qk.stats.admin, queryFn: getAdminStats })
  const projectsQuery = useQuery({ queryKey: qk.projects.list(), queryFn: () => listProjects() })
  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })

  const stats = statsQuery.data
  const projects = projectsQuery.data ?? []
  const facilities = facilitiesQuery.data ?? []

  // Group projects by facility type for the mix chart.
  const byType = Object.entries(
    projects.reduce<Record<string, number>>((accumulator, project) => {
      accumulator[project.facilityType] = (accumulator[project.facilityType] ?? 0) + 1
      return accumulator
    }, {}),
  )
    .map(([type, count]) => ({
      label: FACILITY_TYPE_LABELS[type as keyof typeof FACILITY_TYPE_LABELS] ?? type,
      value: count,
    }))
    .sort((a, b) => b.value - a.value)

  const delayed = projects.filter(
    (project) =>
      project.status !== 'operational' && new Date(project.expectedEndDate).getTime() < Date.now(),
  )

  if (statsQuery.isError) return <ErrorState error={statsQuery.error} />

  return (
    <>
      <PageHeader
        title="التحليلات"
        description="مؤشرات الأداء المجمّعة عبر المنصة — اتجاهات التنفيذ، مزيج المشاريع، ومقارنة أداء المنشآت التشغيلية."
      />

      <Section>
        <KpiGrid>
          <KpiCard
            label="متوسط الإنجاز"
            value={formatPercent(stats?.overallProgress ?? 0)}
            icon="progress"
            tone="primary"
            loading={statsQuery.isPending}
            progress={stats?.overallProgress ?? 0}
          />
          <KpiCard
            label="مشاريع متأخرة"
            value={formatNumber(delayed.length)}
            icon="stages"
            tone={delayed.length > 0 ? 'warning' : 'success'}
            loading={projectsQuery.isPending}
            footnote={
              delayed.length > 0 ? 'تجاوزت تاريخ الانتهاء المتوقع' : 'جميع المشاريع ضمن الجدول'
            }
            footnoteTone={delayed.length > 0 ? 'warning' : 'success'}
          />
          <KpiCard
            label="صحة الأصول"
            value={formatPercent(stats?.assetHealth ?? 0)}
            icon="assetHealth"
            tone="accent"
            loading={statsQuery.isPending}
            progress={stats?.assetHealth ?? 0}
          />
          <KpiCard
            label="المنشآت التشغيلية"
            value={formatNumber(facilities.length)}
            icon="facilities"
            tone="info"
            loading={facilitiesQuery.isPending}
            footnote={`${formatNumber(stats?.totalAssets ?? 0)} أصل مُدار`}
          />
        </KpiGrid>
      </Section>

      <Section>
        <Panel
          title="اتجاه الإنجاز — آخر ستة أشهر"
          subtitle="متوسط نسبة الإنجاز الفعلي مقابل المخطط عبر جميع المشاريع الإنشائية"
        >
          {statsQuery.isPending ? (
            <SkeletonLines count={5} />
          ) : (
            <AreaChart
              data={stats?.progressTrend ?? []}
              xKey="label"
              suffix="%"
              height={280}
              series={[
                { key: 'value', label: 'الإنجاز الفعلي' },
                { key: 'planned', label: 'الإنجاز المخطط' },
              ]}
            />
          )}
        </Panel>
      </Section>

      <Section>
        <SplitGrid even>
          <Panel title="مزيج المشاريع" subtitle="توزيع المشاريع حسب نوع المنشأة">
            {projectsQuery.isPending ? (
              <SkeletonLines count={4} />
            ) : (
              <DonutChart
                slices={byType}
                centerValue={formatNumber(projects.length)}
                centerLabel="مشروع"
                size={200}
              />
            )}
          </Panel>

          <Panel title="حالة الأصول التشغيلية" subtitle="توزيع الأصول حسب حالتها الحالية">
            {statsQuery.isPending ? (
              <SkeletonLines count={4} />
            ) : (
              <DonutChart
                slices={stats?.assetsByStatus ?? []}
                centerValue={formatNumber(stats?.totalAssets ?? 0)}
                centerLabel="أصل"
                size={200}
              />
            )}
          </Panel>
        </SplitGrid>
      </Section>

      <Section>
        <SplitGrid>
          <Panel title="مقارنة أداء المنشآت" subtitle="نسبة الجاهزية التشغيلية (Uptime) لكل منشأة">
            {facilitiesQuery.isPending ? (
              <SkeletonLines count={5} />
            ) : (
              <ComparisonBars
                bars={facilities
                  .slice()
                  .sort((a, b) => b.uptimePercent - a.uptimePercent)
                  .map((facility) => ({
                    label: facility.name,
                    value: facility.uptimePercent,
                    max: 100,
                    tone:
                      facility.uptimePercent >= 96
                        ? 'success'
                        : facility.uptimePercent >= 90
                          ? 'warning'
                          : 'critical',
                    display: `${facility.uptimePercent}%`,
                  }))}
              />
            )}
          </Panel>

          <Panel title="الملخص التنفيذي">
            <p className={shared.hint}>
              تُظهر البيانات الحالية متوسط إنجاز قدره{' '}
              <strong>{formatPercent(stats?.overallProgress ?? 0)}</strong> عبر{' '}
              <strong>{formatNumber(stats?.activeProjects ?? 0)}</strong> مشروعاً نشطاً، مع{' '}
              <strong>{formatNumber(delayed.length)}</strong> مشروعاً تجاوز تاريخ الانتهاء المتوقع
              ويتطلب مراجعة الجدول الزمني.
            </p>
            <p className={shared.hint} style={{ marginTop: 14 }}>
              على الجانب التشغيلي، بلغ متوسط صحة الأصول{' '}
              <strong>{formatPercent(stats?.assetHealth ?? 0)}</strong> مع{' '}
              <strong>{formatNumber(stats?.openWorkOrders ?? 0)}</strong> أمر صيانة مفتوح، منها{' '}
              <strong>{formatNumber(stats?.overdueWorkOrders ?? 0)}</strong> متأخر عن موعده المجدول.
            </p>
            <p className={shared.hint} style={{ marginTop: 14 }}>
              أمنياً، يوجد <strong>{formatNumber(stats?.openIncidents ?? 0)}</strong> حادثاً مفتوحاً
              و<strong>{formatNumber(stats?.criticalAlerts ?? 0)}</strong> تنبيهاً حرجاً بانتظار
              المراجعة من مسؤول الأمن.
            </p>
          </Panel>
        </SplitGrid>
      </Section>
    </>
  )
}
