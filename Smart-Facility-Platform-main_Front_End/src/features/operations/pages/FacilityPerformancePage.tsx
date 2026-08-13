import { useQuery } from '@tanstack/react-query'
import { FACILITY_STATUS_LABELS, FACILITY_STATUS_TONE, FACILITY_TYPE_LABELS } from '@/types'
import { formatDecimal, formatNumber, formatPercent } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { getOperationsStats } from '@/api/stats'
import { listAssets, listFacilities, listFaults, listWorkOrders } from '@/api/operations'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { Panel } from '@/components/ui/Panel/Panel'
import {
  ErrorState,
  ProgressBar,
  SkeletonLines,
  StateCard,
} from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section, SplitGrid } from '@/components/ui/Display/Display'
import { ColumnChart, ComparisonBars } from '@/components/charts/Charts'
import shared from '@/features/shared/Dashboard.module.css'

export function FacilityPerformancePage() {
  const statsQuery = useQuery({ queryKey: qk.stats.operations, queryFn: getOperationsStats })
  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })
  const assetsQuery = useQuery({ queryKey: qk.assets.list(), queryFn: () => listAssets() })
  const ordersQuery = useQuery({ queryKey: qk.workOrders.list(), queryFn: () => listWorkOrders() })
  const faultsQuery = useQuery({ queryKey: qk.faults.list(), queryFn: () => listFaults() })

  const stats = statsQuery.data
  const facilities = facilitiesQuery.data ?? []
  const assets = assetsQuery.data ?? []
  const orders = ordersQuery.data ?? []
  const faults = faultsQuery.data ?? []

  /** Per-facility roll-up — the table and both charts read from this one shape. */
  const rows = facilities.map((facility) => {
    const facilityAssets = assets.filter((asset) => asset.facilityId === facility.id)
    const facilityOrders = orders.filter((order) => order.facilityId === facility.id)
    const facilityFaults = faults.filter((fault) => fault.facilityId === facility.id)

    const health =
      facilityAssets.length === 0
        ? 0
        : Math.round(
            facilityAssets.reduce((sum, asset) => sum + asset.healthScore, 0) /
              facilityAssets.length,
          )

    const completed = facilityOrders.filter((order) => order.status === 'completed').length
    const completionRate =
      facilityOrders.length === 0 ? 0 : Math.round((completed / facilityOrders.length) * 100)

    return {
      facility,
      assetCount: facilityAssets.length,
      health,
      openOrders: facilityOrders.filter((o) => o.status === 'open' || o.status === 'in_progress')
        .length,
      completionRate,
      openFaults: facilityFaults.filter((f) => f.status !== 'resolved').length,
    }
  })

  if (facilitiesQuery.isError) return <ErrorState error={facilitiesQuery.error} />

  return (
    <>
      <PageHeader
        title="كفاءة أداء المنشآت"
        description="مقارنة الجاهزية التشغيلية، صحة الأصول، ومعدل إنجاز الصيانة عبر المنشآت — لتحديد أين يحتاج الأداء تدخلاً."
      />

      <Section>
        <KpiGrid cols={4}>
          <KpiCard
            label="متوسط الجاهزية"
            value={`${formatDecimal(stats?.averageUptime ?? 0)}%`}
            icon="progress"
            tone={(stats?.averageUptime ?? 0) >= 95 ? 'success' : 'warning'}
            loading={statsQuery.isPending}
            progress={stats?.averageUptime ?? 0}
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
            label="صيانة مُنجزة (30 يوماً)"
            value={formatNumber(stats?.completedThisMonth ?? 0)}
            icon="quality"
            tone="success"
            loading={statsQuery.isPending}
          />
          <KpiCard
            label="أوامر متأخرة"
            value={formatNumber(stats?.overdueWorkOrders ?? 0)}
            icon="corrective"
            tone={(stats?.overdueWorkOrders ?? 0) > 0 ? 'critical' : 'success'}
            loading={statsQuery.isPending}
          />
        </KpiGrid>
      </Section>

      <Section>
        <Panel title="أداء الصيانة الشهري" subtitle="عدد أوامر الصيانة المُنجزة عبر آخر ستة أشهر">
          {statsQuery.isPending ? (
            <SkeletonLines count={5} />
          ) : (
            <ColumnChart
              data={stats?.maintenanceTrend ?? []}
              xKey="label"
              valueKey="value"
              label="أوامر مُنجزة"
              height={260}
            />
          )}
        </Panel>
      </Section>

      <Section>
        <SplitGrid even>
          <Panel title="الجاهزية التشغيلية" subtitle="نسبة تشغيل كل منشأة">
            {facilitiesQuery.isPending ? (
              <SkeletonLines count={5} />
            ) : (
              <ComparisonBars
                bars={rows
                  .slice()
                  .sort((a, b) => b.facility.uptimePercent - a.facility.uptimePercent)
                  .map((row) => ({
                    label: row.facility.name,
                    value: row.facility.uptimePercent,
                    max: 100,
                    tone:
                      row.facility.uptimePercent >= 96
                        ? 'success'
                        : row.facility.uptimePercent >= 90
                          ? 'warning'
                          : 'critical',
                    display: `${formatDecimal(row.facility.uptimePercent)}%`,
                  }))}
              />
            )}
          </Panel>

          <Panel title="معدل إنجاز الصيانة" subtitle="نسبة الأوامر المغلقة من الإجمالي">
            {ordersQuery.isPending ? (
              <SkeletonLines count={5} />
            ) : rows.length === 0 ? (
              <StateCard bare title="لا توجد بيانات" />
            ) : (
              <ComparisonBars
                bars={rows
                  .slice()
                  .sort((a, b) => b.completionRate - a.completionRate)
                  .map((row) => ({
                    label: row.facility.name,
                    value: row.completionRate,
                    max: 100,
                    tone:
                      row.completionRate >= 70
                        ? 'success'
                        : row.completionRate >= 40
                          ? 'warning'
                          : 'critical',
                    display: `${row.completionRate}%`,
                  }))}
              />
            )}
          </Panel>
        </SplitGrid>
      </Section>

      <Section>
        <Panel title="مقارنة تفصيلية بين المنشآت" flush>
          <DataTable
            card={false}
            loading={facilitiesQuery.isPending}
            rows={rows}
            rowKey={(row) => row.facility.id}
            columns={[
              {
                key: 'name',
                header: 'المنشأة',
                sortValue: (row) => row.facility.name,
                render: (row) => (
                  <div>
                    <div style={{ fontWeight: 700 }}>{row.facility.name}</div>
                    <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>
                      {FACILITY_TYPE_LABELS[row.facility.type]} · {row.facility.location}
                    </div>
                  </div>
                ),
              },
              {
                key: 'assets',
                header: 'الأصول',
                numeric: true,
                sortValue: (row) => row.assetCount,
                render: (row) => formatNumber(row.assetCount),
              },
              {
                key: 'uptime',
                header: 'الجاهزية',
                width: '160px',
                sortValue: (row) => row.facility.uptimePercent,
                render: (row) => (
                  <ProgressBar value={row.facility.uptimePercent} size="sm" showValue />
                ),
              },
              {
                key: 'health',
                header: 'صحة الأصول',
                width: '160px',
                sortValue: (row) => row.health,
                render: (row) => <ProgressBar value={row.health} size="sm" showValue />,
              },
              {
                key: 'open',
                header: 'أوامر مفتوحة',
                numeric: true,
                sortValue: (row) => row.openOrders,
                render: (row) => formatNumber(row.openOrders),
              },
              {
                key: 'faults',
                header: 'أعطال مفتوحة',
                numeric: true,
                sortValue: (row) => row.openFaults,
                render: (row) => (
                  <span
                    style={{
                      fontWeight: row.openFaults > 0 ? 700 : undefined,
                      color: row.openFaults > 0 ? 'var(--critical-dark)' : undefined,
                    }}
                  >
                    {formatNumber(row.openFaults)}
                  </span>
                ),
              },
              {
                key: 'status',
                header: 'الحالة',
                render: (row) => (
                  <Badge tone={FACILITY_STATUS_TONE[row.facility.status]}>
                    {FACILITY_STATUS_LABELS[row.facility.status]}
                  </Badge>
                ),
              },
            ]}
            empty={<StateCard bare title="لا توجد منشآت" />}
          />
        </Panel>
      </Section>

      <Section>
        <Panel title="الملخص التشغيلي">
          <p className={shared.hint}>
            تعمل <strong>{formatNumber(facilities.length)}</strong> منشآت بمتوسط جاهزية{' '}
            <strong>{formatDecimal(stats?.averageUptime ?? 0)}%</strong> ومتوسط صحة أصول{' '}
            <strong>{formatPercent(stats?.assetHealth ?? 0)}</strong>. أُنجز{' '}
            <strong>{formatNumber(stats?.completedThisMonth ?? 0)}</strong> أمر صيانة خلال آخر 30
            يوماً، ولا يزال <strong>{formatNumber(stats?.openWorkOrders ?? 0)}</strong> أمراً
            مفتوحاً منها <strong>{formatNumber(stats?.overdueWorkOrders ?? 0)}</strong> متأخر عن
            موعده المجدول.
          </p>
        </Panel>
      </Section>
    </>
  )
}
