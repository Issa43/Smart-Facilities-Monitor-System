import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { MapPin } from 'lucide-react'
import {
  ASSET_CATEGORY_LABELS,
  ASSET_STATUS_LABELS,
  ASSET_STATUS_TONE,
  FACILITY_STATUS_LABELS,
  FACILITY_STATUS_TONE,
  FACILITY_TYPE_LABELS,
  FAULT_STATUS_LABELS,
  FAULT_STATUS_TONE,
  PRIORITY_LABELS,
  PRIORITY_TONE,
  SEVERITY_LABELS,
  SEVERITY_TONE,
  WORK_ORDER_STATUS_LABELS,
  WORK_ORDER_STATUS_TONE,
} from '@/types'
import { formatDate, formatDecimal, formatNumber, formatPercent } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { getFacility, listAssets, listFaults, listWorkOrders } from '@/api/operations'
import { listUsers } from '@/api/users'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { Panel } from '@/components/ui/Panel/Panel'
import { Tabs } from '@/components/ui/Tabs/Tabs'
import {
  ErrorState,
  ProgressBar,
  SkeletonLines,
  StateCard,
} from '@/components/ui/Feedback/Feedback'
import { DescriptionList, KpiGrid, Section } from '@/components/ui/Display/Display'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { DonutChart, ProgressRing } from '@/components/charts/Charts'
import { sortByTone } from '@/lib/tone'
import styles from '@/features/shared/ProjectDetail.module.css'

export function FacilityDetailPage() {
  const { facilityId = '' } = useParams<{ facilityId: string }>()
  const navigate = useNavigate()

  const facilityQuery = useQuery({
    queryKey: qk.facilities.detail(facilityId),
    queryFn: () => getFacility(facilityId),
  })
  const assetsQuery = useQuery({
    queryKey: qk.assets.list(facilityId),
    queryFn: () => listAssets(facilityId),
  })
  const workOrdersQuery = useQuery({
    queryKey: qk.workOrders.list(facilityId),
    queryFn: () => listWorkOrders(facilityId),
  })
  const faultsQuery = useQuery({
    queryKey: qk.faults.list(facilityId),
    queryFn: () => listFaults(facilityId),
  })
  const usersQuery = useQuery({ queryKey: qk.users.all, queryFn: listUsers })

  const facility = facilityQuery.data
  const assets = assetsQuery.data ?? []
  const workOrders = workOrdersQuery.data ?? []
  const faults = faultsQuery.data ?? []

  const userName = (id: string | null) =>
    id ? (usersQuery.data?.find((u) => u.id === id)?.fullName ?? '—') : 'غير مُسند'

  if (facilityQuery.isError) return <ErrorState error={facilityQuery.error} />
  if (facilityQuery.isPending || !facility) {
    return (
      <Panel>
        <SkeletonLines count={7} />
      </Panel>
    )
  }

  const averageHealth =
    assets.length === 0
      ? 100
      : Math.round(assets.reduce((sum, asset) => sum + asset.healthScore, 0) / assets.length)
  const openOrders = workOrders.filter((o) => o.status === 'open' || o.status === 'in_progress')
  const openFaults = faults.filter((f) => f.status !== 'resolved')

  const assetsByStatus = sortByTone(
    [
      {
        label: 'يعمل',
        value: assets.filter((a) => a.status === 'operational').length,
        tone: 'success' as const,
      },
      {
        label: 'يحتاج صيانة',
        value: assets.filter((a) => a.status === 'needs_maintenance').length,
        tone: 'warning' as const,
      },
      {
        label: 'تحت الصيانة',
        value: assets.filter((a) => a.status === 'under_maintenance').length,
        tone: 'info' as const,
      },
      {
        label: 'خارج الخدمة',
        value: assets.filter((a) => a.status === 'out_of_service').length,
        tone: 'critical' as const,
      },
    ].filter((slice) => slice.value > 0),
  )

  return (
    <>
      <PageHeader
        title={facility.name}
        description={`منشأة تشغيلية منذ ${formatDate(facility.operationStartDate)} — ${formatNumber(assets.length)} أصل تحت الإدارة.`}
        crumbs={[{ label: facility.name }]}
      />

      <Section>
        <div className={styles.hero}>
          <ProgressRing percent={facility.uptimePercent} size={132} label="الجاهزية" />
          <div className={styles.heroBody}>
            <div className={styles.heroTop}>
              <Badge tone={FACILITY_STATUS_TONE[facility.status]}>
                {FACILITY_STATUS_LABELS[facility.status]}
              </Badge>
              <Badge tone="neutral" plain>
                {FACILITY_TYPE_LABELS[facility.type]}
              </Badge>
            </div>
            <DescriptionList
              items={[
                {
                  label: 'الموقع',
                  value: (
                    <>
                      <MapPin size={13} style={{ display: 'inline', verticalAlign: '-2px' }} />{' '}
                      {facility.location}
                    </>
                  ),
                },
                { label: 'تاريخ بدء التشغيل', value: formatDate(facility.operationStartDate) },
                { label: 'مدير التشغيل', value: userName(facility.operationsManagerId) },
                { label: 'عدد الأصول', value: formatNumber(assets.length) },
                { label: 'متوسط صحة الأصول', value: formatPercent(averageHealth) },
                {
                  label: 'الجاهزية التشغيلية',
                  value: `${formatDecimal(facility.uptimePercent)}%`,
                },
              ]}
            />
          </div>
        </div>
      </Section>

      <Section>
        <KpiGrid>
          <KpiCard
            label="إجمالي الأصول"
            value={formatNumber(assets.length)}
            icon="assets"
            tone="primary"
            loading={assetsQuery.isPending}
          />
          <KpiCard
            label="متوسط صحة الأصول"
            value={formatPercent(averageHealth)}
            icon="assetHealth"
            tone={averageHealth >= 85 ? 'success' : 'warning'}
            loading={assetsQuery.isPending}
            progress={averageHealth}
          />
          <KpiCard
            label="أوامر صيانة مفتوحة"
            value={formatNumber(openOrders.length)}
            icon="maintenance"
            tone={openOrders.length > 0 ? 'warning' : 'success'}
            loading={workOrdersQuery.isPending}
          />
          <KpiCard
            label="أعطال مفتوحة"
            value={formatNumber(openFaults.length)}
            icon="faults"
            tone={openFaults.length > 0 ? 'critical' : 'success'}
            loading={faultsQuery.isPending}
          />
        </KpiGrid>
      </Section>

      <Tabs
        tabs={[
          {
            id: 'overview',
            label: 'نظرة عامة',
            content: (
              <Panel title="توزيع حالة الأصول">
                {assetsQuery.isPending ? (
                  <SkeletonLines count={4} />
                ) : assetsByStatus.length === 0 ? (
                  <StateCard bare title="لا توجد أصول مسجّلة في هذه المنشأة" />
                ) : (
                  <DonutChart
                    slices={assetsByStatus}
                    centerValue={formatNumber(assets.length)}
                    centerLabel="أصل"
                    size={200}
                  />
                )}
              </Panel>
            ),
          },
          {
            id: 'assets',
            label: 'الأصول',
            count: assets.length,
            content: (
              <DataTable
                loading={assetsQuery.isPending}
                rows={assets}
                rowKey={(asset) => asset.id}
                onRowClick={(asset) => navigate(`/operations/assets/${asset.id}`)}
                columns={[
                  {
                    key: 'name',
                    header: 'الأصل',
                    sortValue: (a) => a.name,
                    render: (a) => (
                      <div>
                        <div style={{ fontWeight: 700 }}>{a.name}</div>
                        <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>
                          {a.locationInFacility}
                        </div>
                      </div>
                    ),
                  },
                  {
                    key: 'category',
                    header: 'الفئة',
                    render: (a) => <Badge tone="info">{ASSET_CATEGORY_LABELS[a.category]}</Badge>,
                  },
                  {
                    key: 'serial',
                    header: 'الرقم التسلسلي',
                    render: (a) => <span className="mono">{a.serialNumber}</span>,
                  },
                  {
                    key: 'health',
                    header: 'درجة الصحة',
                    width: '170px',
                    sortValue: (a) => a.healthScore,
                    render: (a) => <ProgressBar value={a.healthScore} size="sm" showValue />,
                  },
                  {
                    key: 'status',
                    header: 'الحالة',
                    render: (a) => (
                      <Badge tone={ASSET_STATUS_TONE[a.status]}>
                        {ASSET_STATUS_LABELS[a.status]}
                      </Badge>
                    ),
                  },
                ]}
                empty={<StateCard bare title="لا توجد أصول" />}
              />
            ),
          },
          {
            id: 'maintenance',
            label: 'الصيانة',
            count: workOrders.length,
            content: (
              <DataTable
                loading={workOrdersQuery.isPending}
                rows={workOrders}
                rowKey={(order) => order.id}
                onRowClick={(order) => navigate(`/operations/work-orders/${order.id}`)}
                columns={[
                  {
                    key: 'ref',
                    header: 'الأمر',
                    sortValue: (o) => o.reference,
                    render: (o) => (
                      <div>
                        <div style={{ fontWeight: 700 }}>{o.reason}</div>
                        <div
                          className="mono"
                          style={{ fontSize: 11.5, color: 'var(--text-muted)' }}
                        >
                          {o.reference}
                        </div>
                      </div>
                    ),
                  },
                  {
                    key: 'type',
                    header: 'النوع',
                    render: (o) => (
                      <Badge tone={o.maintenanceType === 'preventive' ? 'info' : 'warning'}>
                        {o.maintenanceType === 'preventive' ? 'وقائية' : 'تصحيحية'}
                      </Badge>
                    ),
                  },
                  {
                    key: 'priority',
                    header: 'الأولوية',
                    render: (o) => (
                      <Badge tone={PRIORITY_TONE[o.priority]}>{PRIORITY_LABELS[o.priority]}</Badge>
                    ),
                  },
                  {
                    key: 'scheduled',
                    header: 'الموعد',
                    sortValue: (o) => o.scheduledDate,
                    render: (o) => formatDate(o.scheduledDate),
                  },
                  {
                    key: 'status',
                    header: 'الحالة',
                    render: (o) => (
                      <Badge tone={WORK_ORDER_STATUS_TONE[o.status]}>
                        {WORK_ORDER_STATUS_LABELS[o.status]}
                      </Badge>
                    ),
                  },
                ]}
                empty={<StateCard bare title="لا توجد أوامر صيانة" />}
              />
            ),
          },
          {
            id: 'faults',
            label: 'الأعطال',
            count: faults.length,
            content: (
              <DataTable
                loading={faultsQuery.isPending}
                rows={faults}
                rowKey={(fault) => fault.id}
                columns={[
                  {
                    key: 'ref',
                    header: 'العطل',
                    sortValue: (f) => f.reference,
                    render: (f) => (
                      <div>
                        <div style={{ fontWeight: 700 }}>{f.faultType}</div>
                        <div
                          className="mono"
                          style={{ fontSize: 11.5, color: 'var(--text-muted)' }}
                        >
                          {f.reference}
                        </div>
                      </div>
                    ),
                  },
                  { key: 'desc', header: 'الوصف', render: (f) => f.description },
                  {
                    key: 'severity',
                    header: 'الخطورة',
                    render: (f) => (
                      <Badge tone={SEVERITY_TONE[f.severity]}>{SEVERITY_LABELS[f.severity]}</Badge>
                    ),
                  },
                  {
                    key: 'discovered',
                    header: 'وقت الاكتشاف',
                    sortValue: (f) => f.discoveredAt,
                    render: (f) => formatDate(f.discoveredAt),
                  },
                  {
                    key: 'status',
                    header: 'الحالة',
                    render: (f) => (
                      <Badge tone={FAULT_STATUS_TONE[f.status]}>
                        {FAULT_STATUS_LABELS[f.status]}
                      </Badge>
                    ),
                  },
                ]}
                empty={<StateCard bare title="لا توجد أعطال مسجّلة" />}
              />
            ),
          },
        ]}
      />
    </>
  )
}
