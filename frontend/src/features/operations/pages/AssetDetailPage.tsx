import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { MapPin } from 'lucide-react'
import type { AssetStatus } from '@/types'
import {
  assetCategoryLabel,
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
import {
  deleteAsset,
  getAsset,
  getAssetFilterOptions,
  getFacility,
  listFaults,
  listWorkOrders,
  transitionAssetStatus,
  updateAsset,
} from '@/api/operations'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button, LinkButton } from '@/components/ui/Button/Button'
import { Panel } from '@/components/ui/Panel/Panel'
import { Tabs } from '@/components/ui/Tabs/Tabs'
import { Alert, ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { DescriptionList, KpiGrid, Section, Timeline } from '@/components/ui/Display/Display'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { ProgressRing } from '@/components/charts/Charts'
import shared from '@/features/shared/Dashboard.module.css'
import styles from '@/features/shared/ProjectDetail.module.css'
import {
  AssetEditModal,
  type AssetEditValues,
} from '@/features/operations/components/AssetEditModal'

const ALLOWED_TRANSITIONS: Record<AssetStatus, AssetStatus[]> = {
  operational: ['under_maintenance', 'out_of_service'],
  under_maintenance: ['operational', 'out_of_service'],
  out_of_service: ['under_maintenance'],
}

export function AssetDetailPage() {
  const { assetId = '' } = useParams<{ assetId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [editOpen, setEditOpen] = useState(false)

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
  const optionsQuery = useQuery({
    queryKey: [...qk.assets.all, 'filter-options'],
    queryFn: getAssetFilterOptions,
  })
  const ordersQuery = useQuery({
    queryKey: [...qk.workOrders.list(), assetId],
    queryFn: () => listWorkOrders(undefined, assetId),
  })
  const faultsQuery = useQuery({
    queryKey: [...qk.faults.list(), assetId],
    queryFn: () => listFaults(undefined, assetId),
  })

  const changeStatus = useMutation({
    mutationFn: (status: AssetStatus) => transitionAssetStatus(assetId, status),
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

  const edit = useMutation({
    mutationFn: (values: AssetEditValues) => updateAsset(assetId, values),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: qk.assets.all })
      queryClient.invalidateQueries({ queryKey: qk.facilities.all })
      setEditOpen(false)
      showToast({ tone: 'success', title: 'تم تحديث الأصل', description: updated.name })
    },
  })
  const archive = useMutation({
    mutationFn: () => deleteAsset(assetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.assets.all })
      queryClient.invalidateQueries({ queryKey: qk.facilities.all })
      showToast({ tone: 'success', title: 'تمت أرشفة الأصل' })
      navigate('/operations/assets')
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

  const assetOrders = ordersQuery.data ?? []
  const assetFaults = faultsQuery.data ?? []
  const openOrders = assetOrders.filter((o) =>
    ['open', 'assigned', 'in_progress'].includes(o.status),
  )

  return (
    <>
      <PageHeader
        title={asset.name}
        description={`${assetCategoryLabel(asset.category)} — ${asset.locationInFacility}`}
        crumbs={[{ label: asset.name }]}
        actions={
          <>
            <Button variant="ghost" onClick={() => setEditOpen(true)}>
              تعديل الأصل
            </Button>
            <Button
              variant="critical"
              loading={archive.isPending}
              onClick={() => {
                if (window.confirm('هل تريد أرشفة هذا الأصل؟ لا يمكن أرشفة أصل لديه سجل تشغيلي.'))
                  archive.mutate()
              }}
            >
              أرشفة الأصل
            </Button>
            <LinkButton to="/operations/work-orders" variant="ghost">
              أوامر الصيانة
            </LinkButton>
            <LinkButton to="/operations/faults">تسجيل عطل</LinkButton>
          </>
        }
      />

      <Section>
        {archive.isError && (
          <Alert
            tone="critical"
            title="تعذر أرشفة الأصل"
            description={(archive.error as Error).message}
          />
        )}
        <div className={styles.hero}>
          <ProgressRing percent={asset.healthScore} size={132} label="درجة الصحة" />
          <div className={styles.heroBody}>
            <div className={styles.heroTop}>
              <Badge tone={ASSET_STATUS_TONE[asset.status]}>
                {ASSET_STATUS_LABELS[asset.status]}
              </Badge>
              <Badge tone="neutral" plain>
                {assetCategoryLabel(asset.category)}
              </Badge>
            </div>
            <DescriptionList
              items={[
                {
                  label: 'نوع الأصل',
                  value: asset.assetType || '—',
                },
                {
                  label: 'الشركة المصنعة / الطراز',
                  value: `${asset.manufacturer || '—'} / ${asset.model || '—'}`,
                },
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
                {
                  label: 'تاريخ التشغيل',
                  value: asset.commissionDate ? formatDate(asset.commissionDate) : '—',
                },
                {
                  label: 'تاريخ الإنشاء',
                  value: asset.createdAt ? formatDate(asset.createdAt) : '—',
                },
                { label: 'آخر تحديث', value: formatRelative(asset.updatedAt) },
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
            value={
              asset.remainingUsefulLife == null ? '—' : formatNumber(asset.remainingUsefulLife)
            }
            icon="progress"
            tone="info"
            footnote="القيمة المسجلة في نظام إدارة الأصول؛ لا تُستنتج من درجة الصحة"
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
            footnote={`${formatNumber(assetFaults.filter((f) => f.status !== 'closed').length)} عطل مفتوح`}
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
                    {ALLOWED_TRANSITIONS[asset.status].map((status) => (
                      <button
                        key={status}
                        type="button"
                        className={shared.attentionRow}
                        onClick={() => changeStatus.mutate(status)}
                        disabled={changeStatus.isPending}
                      >
                        <span style={{ flex: 1, minWidth: 0 }}>
                          <span className={shared.attentionTitle}>
                            {ASSET_STATUS_LABELS[status]}
                          </span>
                        </span>
                      </button>
                    ))}
                  </div>
                  {changeStatus.isError && (
                    <Alert
                      tone="critical"
                      title="تعذر تغيير حالة الأصل"
                      description={(changeStatus.error as Error).message}
                    />
                  )}
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
      <AssetEditModal
        asset={asset}
        open={editOpen}
        onClose={() => setEditOpen(false)}
        onSave={(values) => edit.mutate(values)}
        saving={edit.isPending}
        error={edit.isError ? (edit.error as Error) : null}
        options={optionsQuery.data}
      />
    </>
  )
}
