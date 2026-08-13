import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { MapPin } from 'lucide-react'
import type { AssetStatus } from '@/types'
import {
  ASSET_CATEGORY_LABELS,
  ASSET_STATUS_LABELS,
  ASSET_STATUS_TONE,
  FAULT_STATUS_LABELS,
  FAULT_STATUS_TONE,
  SEVERITY_LABELS,
  SEVERITY_TONE,
  WORK_ORDER_STATUS_LABELS,
  WORK_ORDER_STATUS_TONE,
} from '@/types'
import { formatDate, formatNumber, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { getAsset, getFacility, listFaults, listWorkOrders, updateAsset } from '@/api/operations'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { LinkButton } from '@/components/ui/Button/Button'
import { Panel } from '@/components/ui/Panel/Panel'
import { Tabs } from '@/components/ui/Tabs/Tabs'
import { ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { DescriptionList, KpiGrid, Section, Timeline } from '@/components/ui/Display/Display'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { ProgressRing } from '@/components/charts/Charts'
import shared from '@/features/shared/Dashboard.module.css'
import styles from '@/features/shared/ProjectDetail.module.css'

export function AssetDetailPage() {
  const { assetId = '' } = useParams<{ assetId: string }>()
  const queryClient = useQueryClient()
  const { showToast } = useToast()

  const assetQuery = useQuery({
    queryKey: qk.assets.detail(assetId),
    queryFn: () => getAsset(assetId),
  })
  const asset = assetQuery.data

  const facilityQuery = useQuery({
    queryKey: qk.facilities.detail(asset?.facilityId ?? ''),
    queryFn: () => getFacility(asset?.facilityId as string),
    enabled: Boolean(asset?.facilityId),
  })
  const ordersQuery = useQuery({ queryKey: qk.workOrders.list(), queryFn: () => listWorkOrders() })
  const faultsQuery = useQuery({ queryKey: qk.faults.list(), queryFn: () => listFaults() })

  const changeStatus = useMutation({
    mutationFn: (status: AssetStatus) => updateAsset(assetId, { status }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: qk.assets.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.operations })
      showToast({
        tone: 'success',
        title: 'تم تحديث حالة الأصل',
        description: ASSET_STATUS_LABELS[updated.status],
      })
    },
  })

  if (assetQuery.isError) return <ErrorState error={assetQuery.error} />
  if (assetQuery.isPending || !asset) {
    return (
      <Panel>
        <SkeletonLines count={7} />
      </Panel>
    )
  }

  const assetOrders = (ordersQuery.data ?? []).filter((order) => order.assetId === asset.id)
  const assetFaults = (faultsQuery.data ?? []).filter((fault) => fault.assetId === asset.id)
  const openOrders = assetOrders.filter((o) => o.status === 'open' || o.status === 'in_progress')

  /**
   * Remaining useful life, estimated from health score against a nominal
   * fifteen-year design life. A real CMMS would derive this from run hours and
   * failure history; here the basis is stated rather than presented as fact.
   */
  const remainingYears = Math.round((asset.healthScore / 100) * 15 * 10) / 10

  return (
    <>
      <PageHeader
        title={asset.name}
        description={`${ASSET_CATEGORY_LABELS[asset.category]} — ${asset.locationInFacility}`}
        crumbs={[{ label: asset.name }]}
        actions={
          <>
            <LinkButton to="/operations/work-orders" variant="ghost">
              أوامر الصيانة
            </LinkButton>
            <LinkButton to="/operations/faults">تسجيل عطل</LinkButton>
          </>
        }
      />

      <Section>
        <div className={styles.hero}>
          <ProgressRing percent={asset.healthScore} size={132} label="درجة الصحة" />
          <div className={styles.heroBody}>
            <div className={styles.heroTop}>
              <Badge tone={ASSET_STATUS_TONE[asset.status]}>
                {ASSET_STATUS_LABELS[asset.status]}
              </Badge>
              <Badge tone="neutral" plain>
                {ASSET_CATEGORY_LABELS[asset.category]}
              </Badge>
            </div>
            <DescriptionList
              items={[
                {
                  label: 'المنشأة',
                  value: facilityQuery.data ? (
                    <Link
                      to={`/operations/facilities/${facilityQuery.data.id}`}
                      style={{ color: 'var(--primary-dark)', fontWeight: 700 }}
                    >
                      {facilityQuery.data.name}
                    </Link>
                  ) : (
                    '—'
                  ),
                },
                {
                  label: 'الموقع داخل المنشأة',
                  value: (
                    <>
                      <MapPin size={13} style={{ display: 'inline', verticalAlign: '-2px' }} />{' '}
                      {asset.locationInFacility}
                    </>
                  ),
                },
                {
                  label: 'الرقم التسلسلي',
                  value: <span className="mono">{asset.serialNumber}</span>,
                },
                { label: 'تاريخ التركيب', value: formatDate(asset.installDate) },
                { label: 'تاريخ التشغيل', value: formatDate(asset.commissionDate) },
                {
                  label: 'آخر صيانة',
                  value: asset.lastMaintenanceAt
                    ? formatRelative(asset.lastMaintenanceAt)
                    : 'لم تُجرَ صيانة بعد',
                },
              ]}
            />
          </div>
        </div>
      </Section>

      <Section>
        <KpiGrid>
          <KpiCard
            label="درجة الصحة"
            value={`${formatNumber(asset.healthScore)}`}
            icon="assetHealth"
            tone={
              asset.healthScore >= 85 ? 'success' : asset.healthScore >= 60 ? 'warning' : 'critical'
            }
            progress={asset.healthScore}
          />
          <KpiCard
            label="العمر التشغيلي المتبقي"
            value={`${remainingYears} سنة`}
            icon="progress"
            tone="info"
            footnote="تقدير مبني على درجة الصحة وعمر تصميمي 15 سنة"
          />
          <KpiCard
            label="أوامر صيانة مفتوحة"
            value={formatNumber(openOrders.length)}
            icon="maintenance"
            tone={openOrders.length > 0 ? 'warning' : 'success'}
            loading={ordersQuery.isPending}
            footnote={`${formatNumber(assetOrders.length)} أمر إجمالاً`}
          />
          <KpiCard
            label="الأعطال المسجّلة"
            value={formatNumber(asset.faultCount)}
            icon="faults"
            tone={asset.faultCount > 2 ? 'critical' : 'neutral'}
            footnote={`${formatNumber(assetFaults.filter((f) => f.status !== 'resolved').length)} عطل مفتوح`}
          />
        </KpiGrid>
      </Section>

      <Tabs
        tabs={[
          {
            id: 'overview',
            label: 'نظرة عامة',
            content: (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1.4fr 1fr',
                  gap: 16,
                  alignItems: 'start',
                }}
              >
                <Panel title="ملاحظات فنية">
                  <p className={shared.hint}>
                    {asset.notes || 'لا توجد ملاحظات مسجّلة على هذا الأصل.'}
                  </p>
                </Panel>

                <Panel title="تحديث حالة الأصل">
                  <p className={shared.hint} style={{ marginBottom: 14 }}>
                    تُحدَّث الحالة تلقائياً عند تسجيل عطل أو إغلاق أمر صيانة، ويمكن تعديلها يدوياً
                    عند الحاجة.
                  </p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {(Object.keys(ASSET_STATUS_LABELS) as AssetStatus[]).map((status) => (
                      <button
                        key={status}
                        type="button"
                        className={shared.attentionRow}
                        onClick={() => changeStatus.mutate(status)}
                        disabled={status === asset.status || changeStatus.isPending}
                        style={{
                          opacity: status === asset.status ? 0.55 : 1,
                          cursor: status === asset.status ? 'default' : 'pointer',
                        }}
                      >
                        <span style={{ flex: 1, minWidth: 0 }}>
                          <span className={shared.attentionTitle}>
                            {ASSET_STATUS_LABELS[status]}
                          </span>
                        </span>
                        {status === asset.status && <Badge tone="info">الحالة الحالية</Badge>}
                      </button>
                    ))}
                  </div>
                </Panel>
              </div>
            ),
          },
          {
            id: 'maintenance',
            label: 'سجل الصيانة',
            count: assetOrders.length,
            content: (
              <Panel title="أوامر الصيانة على هذا الأصل">
                {ordersQuery.isPending ? (
                  <SkeletonLines count={5} />
                ) : assetOrders.length === 0 ? (
                  <StateCard bare title="لا توجد أوامر صيانة" />
                ) : (
                  <Timeline
                    entries={assetOrders
                      .slice()
                      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
                      .map((order) => ({
                        id: order.id,
                        tone: WORK_ORDER_STATUS_TONE[order.status],
                        title: (
                          <Link to={`/operations/work-orders/${order.id}`}>
                            {order.reason}{' '}
                            <Badge tone={WORK_ORDER_STATUS_TONE[order.status]}>
                              {WORK_ORDER_STATUS_LABELS[order.status]}
                            </Badge>
                          </Link>
                        ),
                        body: order.description,
                        meta: `${order.reference} · ${order.maintenanceType === 'preventive' ? 'وقائية' : 'تصحيحية'} · ${formatDate(order.scheduledDate)}`,
                      }))}
                  />
                )}
              </Panel>
            ),
          },
          {
            id: 'faults',
            label: 'سجل الأعطال',
            count: assetFaults.length,
            content: (
              <Panel title="الأعطال المسجّلة على هذا الأصل">
                {faultsQuery.isPending ? (
                  <SkeletonLines count={4} />
                ) : assetFaults.length === 0 ? (
                  <StateCard bare title="لا توجد أعطال مسجّلة" description="أصل بسجل نظيف." />
                ) : (
                  <Timeline
                    entries={assetFaults
                      .slice()
                      .sort((a, b) => b.discoveredAt.localeCompare(a.discoveredAt))
                      .map((fault) => ({
                        id: fault.id,
                        tone: FAULT_STATUS_TONE[fault.status],
                        title: (
                          <>
                            {fault.faultType}{' '}
                            <Badge tone={SEVERITY_TONE[fault.severity]}>
                              {SEVERITY_LABELS[fault.severity]}
                            </Badge>
                          </>
                        ),
                        body: (
                          <>
                            {fault.description}
                            {fault.rootCause && (
                              <span
                                style={{
                                  display: 'block',
                                  marginTop: 4,
                                  color: 'var(--text-faint)',
                                }}
                              >
                                السبب الجذري: {fault.rootCause}
                              </span>
                            )}
                          </>
                        ),
                        meta: `${fault.reference} · ${FAULT_STATUS_LABELS[fault.status]} · ${formatDate(fault.discoveredAt)}`,
                      }))}
                  />
                )}
              </Panel>
            ),
          },
        ]}
      />
    </>
  )
}
