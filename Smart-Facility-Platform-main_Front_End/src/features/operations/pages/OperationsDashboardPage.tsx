import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import {
  FACILITY_STATUS_LABELS,
  FACILITY_STATUS_TONE,
  FACILITY_TYPE_LABELS,
  PRIORITY_LABELS,
  PRIORITY_TONE,
  WORK_ORDER_STATUS_LABELS,
  WORK_ORDER_STATUS_TONE,
} from '@/types'
import { formatDate, formatDecimal, formatNumber, formatPercent } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { getOperationsStats } from '@/api/stats'
import { listAssets, listFacilities, listFaults, listWorkOrders } from '@/api/operations'
import { PageHeader } from '@/components/layout/PageHeader'
import { Icon } from '@/components/icons'
import { Badge } from '@/components/ui/Badge/Badge'
import { LinkButton } from '@/components/ui/Button/Button'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { Panel } from '@/components/ui/Panel/Panel'
import {
  ErrorState,
  ProgressBar,
  SkeletonLines,
  StateCard,
} from '@/components/ui/Feedback/Feedback'
import { KpiGrid, Section } from '@/components/ui/Display/Display'
import { ColumnChart, DonutChart } from '@/components/charts/Charts'
import { STATUS_COLORS } from '@/components/charts/chartTheme'
import shared from '@/features/shared/Dashboard.module.css'

const QUICK_ACTIONS = [
  { to: '/operations/work-orders', icon: 'maintenance', label: 'أمر صيانة', hint: 'إنشاء ومتابعة' },
  { to: '/operations/faults', icon: 'faults', label: 'تسجيل عطل', hint: 'بلاغ جديد' },
  { to: '/operations/assets', icon: 'assets', label: 'إدارة الأصول', hint: 'إضافة وتحديث' },
  { to: '/operations/reports', icon: 'reports', label: 'تقرير تشغيلي', hint: 'إصدار وتصدير' },
] as const

export function OperationsDashboardPage() {
  const statsQuery = useQuery({ queryKey: qk.stats.operations, queryFn: getOperationsStats })
  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })
  const workOrdersQuery = useQuery({
    queryKey: qk.workOrders.list(),
    queryFn: () => listWorkOrders(),
  })
  const faultsQuery = useQuery({ queryKey: qk.faults.list(), queryFn: () => listFaults() })
  const assetsQuery = useQuery({ queryKey: qk.assets.list(), queryFn: () => listAssets() })

  const stats = statsQuery.data
  const openOrders =
    workOrdersQuery.data
      ?.filter((order) => order.status === 'open' || order.status === 'in_progress')
      .sort((a, b) => a.scheduledDate.localeCompare(b.scheduledDate))
      .slice(0, 6) ?? []
  const openFaults = faultsQuery.data?.filter((fault) => fault.status !== 'resolved') ?? []
  const criticalAssets =
    assetsQuery.data
      ?.filter((asset) => asset.healthScore < 75)
      .sort((a, b) => a.healthScore - b.healthScore)
      .slice(0, 5) ?? []

  if (statsQuery.isError) return <ErrorState error={statsQuery.error} />

  return (
    <>
      <PageHeader
        title={
          <>
            لوحة التشغيل الرئيسية
            <span
              className={
                (stats?.outOfServiceAssets ?? 0) > 0
                  ? `${shared.livePill} ${shared.livePillCritical}`
                  : shared.livePill
              }
            >
              <span className={shared.liveDot} />
              {(stats?.outOfServiceAssets ?? 0) > 0
                ? `${formatNumber(stats?.outOfServiceAssets ?? 0)} أصل خارج الخدمة`
                : 'جميع الأصول تعمل'}
            </span>
          </>
        }
        description="إدارة الأصول وأعمال الصيانة والأعطال عبر المنشآت التشغيلية، ومتابعة جاهزيتها التشغيلية."
        actions={
          <>
            <LinkButton to="/operations/asset-health" variant="ghost">
              مركز صحة الأصول
            </LinkButton>
            <LinkButton to="/operations/work-orders">أوامر الصيانة</LinkButton>
          </>
        }
      />

      <Section>
        <KpiGrid>
          <KpiCard
            label="المنشآت التشغيلية"
            value={formatNumber(stats?.facilities ?? 0)}
            icon="facilities"
            tone="primary"
            loading={statsQuery.isPending}
            footnote={`متوسط الجاهزية ${formatDecimal(stats?.averageUptime ?? 0)}%`}
          />
          <KpiCard
            label="إجمالي الأصول"
            value={formatNumber(stats?.totalAssets ?? 0)}
            icon="assets"
            tone="info"
            loading={statsQuery.isPending}
            footnote={`${formatNumber(stats?.operationalAssets ?? 0)} أصل يعمل`}
          />
          <KpiCard
            label="متوسط صحة الأصول"
            value={formatPercent(stats?.assetHealth ?? 0)}
            icon="assetHealth"
            tone={(stats?.assetHealth ?? 0) >= 85 ? 'success' : 'warning'}
            loading={statsQuery.isPending}
            progress={stats?.assetHealth ?? 0}
          />
          <KpiCard
            label="أصول خارج الخدمة"
            value={formatNumber(stats?.outOfServiceAssets ?? 0)}
            icon="corrective"
            tone={(stats?.outOfServiceAssets ?? 0) > 0 ? 'critical' : 'success'}
            loading={statsQuery.isPending}
            footnote={
              (stats?.outOfServiceAssets ?? 0) > 0 ? 'تتطلب تدخلاً عاجلاً' : 'لا توجد أصول متوقفة'
            }
            footnoteTone={(stats?.outOfServiceAssets ?? 0) > 0 ? 'critical' : 'success'}
          />
          <KpiCard
            label="أوامر صيانة مفتوحة"
            value={formatNumber(stats?.openWorkOrders ?? 0)}
            icon="maintenance"
            tone="warning"
            loading={statsQuery.isPending}
            footnote={`${formatNumber(stats?.overdueWorkOrders ?? 0)} متأخرة عن موعدها`}
            footnoteTone="warning"
          />
          <KpiCard
            label="صيانة مُنجزة هذا الشهر"
            value={formatNumber(stats?.completedThisMonth ?? 0)}
            icon="quality"
            tone="success"
            loading={statsQuery.isPending}
            footnote="أوامر مغلقة خلال 30 يوماً"
          />
          <KpiCard
            label="أعطال مفتوحة"
            value={formatNumber(stats?.openFaults ?? 0)}
            icon="faults"
            tone={(stats?.openFaults ?? 0) > 0 ? 'warning' : 'success'}
            loading={statsQuery.isPending}
            footnote={`${formatNumber(stats?.criticalFaults ?? 0)} عطل حرج`}
            footnoteTone={(stats?.criticalFaults ?? 0) > 0 ? 'critical' : 'success'}
          />
          <KpiCard
            label="متوسط الجاهزية"
            value={`${formatDecimal(stats?.averageUptime ?? 0)}%`}
            icon="progress"
            tone="accent"
            loading={statsQuery.isPending}
            progress={stats?.averageUptime ?? 0}
          />
        </KpiGrid>
      </Section>

      <Section>
        <div className={shared.chartRow}>
          <Panel
            title="أداء الصيانة"
            subtitle="عدد أوامر الصيانة المُنجزة شهرياً خلال آخر ستة أشهر"
          >
            {statsQuery.isPending ? (
              <SkeletonLines count={5} />
            ) : (
              <ColumnChart
                data={stats?.maintenanceTrend ?? []}
                xKey="label"
                valueKey="value"
                label="أوامر مُنجزة"
              />
            )}
          </Panel>

          <Panel title="حالة الأصول" subtitle="توزيع الأصول حسب حالتها التشغيلية">
            {statsQuery.isPending ? (
              <SkeletonLines count={4} />
            ) : (
              <DonutChart
                slices={stats?.assetsByStatus ?? []}
                centerValue={formatNumber(stats?.totalAssets ?? 0)}
                centerLabel="أصل"
              />
            )}
          </Panel>
        </div>
      </Section>

      <Section>
        <div className={shared.chartRow}>
          <Panel
            title="أوامر الصيانة المفتوحة"
            actions={
              <Link to="/operations/work-orders" className={shared.metricLabel}>
                عرض الكل <ArrowLeft size={12} style={{ display: 'inline' }} />
              </Link>
            }
          >
            {workOrdersQuery.isPending ? (
              <SkeletonLines count={5} />
            ) : openOrders.length === 0 ? (
              <StateCard bare title="لا توجد أوامر صيانة مفتوحة" />
            ) : (
              <div className={shared.attentionList}>
                {openOrders.map((order) => {
                  const overdue = new Date(order.scheduledDate).getTime() < Date.now()
                  return (
                    <Link
                      key={order.id}
                      to={`/operations/work-orders/${order.id}`}
                      className={shared.attentionRow}
                    >
                      <span
                        className={shared.attentionBar}
                        style={{
                          background: overdue ? STATUS_COLORS.critical : STATUS_COLORS.warning,
                        }}
                      />
                      <span style={{ flex: 1, minWidth: 0 }}>
                        <span className={shared.attentionTitle}>{order.reason}</span>
                        <span className={shared.attentionMeta}>
                          <span className="mono">{order.reference}</span> ·{' '}
                          {formatDate(order.scheduledDate)}
                          {overdue && ' — متأخر'}
                        </span>
                      </span>
                      <Badge tone={PRIORITY_TONE[order.priority]}>
                        {PRIORITY_LABELS[order.priority]}
                      </Badge>
                      <Badge tone={WORK_ORDER_STATUS_TONE[order.status]}>
                        {WORK_ORDER_STATUS_LABELS[order.status]}
                      </Badge>
                    </Link>
                  )
                })}
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
              <div className={shared.metricRow}>
                <span className={shared.metricLabel}>أعطال مفتوحة</span>
                <span className={shared.metricValue}>{formatNumber(openFaults.length)}</span>
              </div>
              <div className={shared.metricRow}>
                <span className={shared.metricLabel}>أعطال حرجة</span>
                <span className={shared.metricValue} style={{ color: 'var(--critical-dark)' }}>
                  {formatNumber(stats?.criticalFaults ?? 0)}
                </span>
              </div>
              <div className={shared.metricRow}>
                <span className={shared.metricLabel}>أصول تحتاج صيانة</span>
                <span className={shared.metricValue}>
                  {formatNumber(
                    assetsQuery.data?.filter((a) => a.status === 'needs_maintenance').length ?? 0,
                  )}
                </span>
              </div>
            </div>
          </Panel>
        </div>
      </Section>

      <Section>
        <div className={shared.chartRow}>
          <Panel
            title="المنشآت التشغيلية"
            actions={
              <Link to="/operations/facilities" className={shared.metricLabel}>
                عرض الكل <ArrowLeft size={12} style={{ display: 'inline' }} />
              </Link>
            }
          >
            {facilitiesQuery.isPending ? (
              <SkeletonLines count={4} />
            ) : (
              <div className={shared.strip}>
                {facilitiesQuery.data?.map((facility) => (
                  <Link
                    key={facility.id}
                    to={`/operations/facilities/${facility.id}`}
                    className={shared.stripCard}
                  >
                    <div className={shared.stripHead}>
                      <div>
                        <span className={shared.stripName}>{facility.name}</span>
                        <span className={shared.stripMeta}>
                          {FACILITY_TYPE_LABELS[facility.type]} ·{' '}
                          {formatNumber(facility.assetCount)} أصل
                        </span>
                      </div>
                      <Badge tone={FACILITY_STATUS_TONE[facility.status]}>
                        {FACILITY_STATUS_LABELS[facility.status]}
                      </Badge>
                    </div>
                    <ProgressBar
                      value={facility.uptimePercent}
                      size="sm"
                      label={`جاهزية ${facility.name}`}
                    />
                    <div className={shared.stripFoot}>
                      <span>الجاهزية التشغيلية</span>
                      <span>{formatDecimal(facility.uptimePercent)}%</span>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </Panel>

          <Panel
            title="أصول تحتاج انتباهاً"
            subtitle="الأصول الأقل في درجة الصحة"
            actions={
              <Link to="/operations/asset-health" className={shared.metricLabel}>
                التفاصيل <ArrowLeft size={12} style={{ display: 'inline' }} />
              </Link>
            }
          >
            {assetsQuery.isPending ? (
              <SkeletonLines count={4} />
            ) : criticalAssets.length === 0 ? (
              <StateCard bare title="جميع الأصول بحالة جيدة" />
            ) : (
              <div className={shared.metricList}>
                {criticalAssets.map((asset) => (
                  <div key={asset.id}>
                    <div className={shared.metricRow} style={{ marginBottom: 6 }}>
                      <Link to={`/operations/assets/${asset.id}`} className={shared.metricLabel}>
                        {asset.name}
                      </Link>
                      <span className={shared.metricValue}>{formatPercent(asset.healthScore)}</span>
                    </div>
                    <ProgressBar value={asset.healthScore} size="sm" label={asset.name} />
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      </Section>
    </>
  )
}
