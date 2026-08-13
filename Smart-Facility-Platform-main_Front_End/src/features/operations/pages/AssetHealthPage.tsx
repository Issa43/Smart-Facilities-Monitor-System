import { useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ASSET_CATEGORY_LABELS, ASSET_STATUS_LABELS, ASSET_STATUS_TONE } from '@/types'
import { formatDate, formatNumber, formatPercent } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { getOperationsStats } from '@/api/stats'
import { listAssets, listFacilities } from '@/api/operations'
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
import { ComparisonBars, DonutChart, ProgressRing } from '@/components/charts/Charts'
import shared from '@/features/shared/Dashboard.module.css'

/** Health bands. Kept here so the ring, the table and the summary all agree. */
function healthBand(score: number): { label: string; tone: 'success' | 'warning' | 'critical' } {
  if (score >= 85) return { label: 'ممتازة', tone: 'success' }
  if (score >= 70) return { label: 'جيدة', tone: 'success' }
  if (score >= 50) return { label: 'متوسطة', tone: 'warning' }
  return { label: 'حرجة', tone: 'critical' }
}

export function AssetHealthPage() {
  const navigate = useNavigate()

  const statsQuery = useQuery({ queryKey: qk.stats.operations, queryFn: getOperationsStats })
  const assetsQuery = useQuery({ queryKey: qk.assets.list(), queryFn: () => listAssets() })
  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })

  const assets = assetsQuery.data ?? []
  const stats = statsQuery.data

  const facilityName = useCallback(
    (id: string) => facilitiesQuery.data?.find((f) => f.id === id)?.name ?? '—',
    [facilitiesQuery.data],
  )

  const averageHealth =
    assets.length === 0
      ? 100
      : Math.round(assets.reduce((sum, asset) => sum + asset.healthScore, 0) / assets.length)

  const bands = [
    {
      label: 'ممتازة (85+)',
      value: assets.filter((a) => a.healthScore >= 85).length,
      tone: 'success' as const,
    },
    {
      label: 'جيدة (70–84)',
      value: assets.filter((a) => a.healthScore >= 70 && a.healthScore < 85).length,
      tone: 'info' as const,
    },
    {
      label: 'متوسطة (50–69)',
      value: assets.filter((a) => a.healthScore >= 50 && a.healthScore < 70).length,
      tone: 'warning' as const,
    },
    {
      label: 'حرجة (<50)',
      value: assets.filter((a) => a.healthScore < 50).length,
      tone: 'critical' as const,
    },
  ].filter((band) => band.value > 0)

  /** Mean health per facility — which building is dragging the average down. */
  const byFacility = (facilitiesQuery.data ?? [])
    .map((facility) => {
      const facilityAssets = assets.filter((asset) => asset.facilityId === facility.id)
      const mean =
        facilityAssets.length === 0
          ? 0
          : Math.round(
              facilityAssets.reduce((sum, asset) => sum + asset.healthScore, 0) /
                facilityAssets.length,
            )
      return { label: facility.name, value: mean, max: 100, tone: healthBand(mean).tone }
    })
    .filter((row) => row.value > 0)
    .sort((a, b) => b.value - a.value)

  const critical = assets
    .filter((asset) => asset.healthScore < 75)
    .sort((a, b) => a.healthScore - b.healthScore)

  if (assetsQuery.isError) return <ErrorState error={assetsQuery.error} />

  return (
    <>
      <PageHeader
        title="مركز صحة الأصول"
        description="درجة الصحة تُحتسب من سجل الأعطال وأعمال الصيانة: كل عطل يخفضها، وكل أمر صيانة مكتمل يرفعها."
      />

      <Section>
        <KpiGrid cols={4}>
          <KpiCard
            label="متوسط صحة الأصول"
            value={formatPercent(averageHealth)}
            icon="assetHealth"
            tone={healthBand(averageHealth).tone === 'critical' ? 'critical' : 'success'}
            loading={assetsQuery.isPending}
            progress={averageHealth}
          />
          <KpiCard
            label="أصول بحالة ممتازة"
            value={formatNumber(assets.filter((a) => a.healthScore >= 85).length)}
            icon="quality"
            tone="success"
            loading={assetsQuery.isPending}
            footnote={`من إجمالي ${formatNumber(assets.length)} أصل`}
          />
          <KpiCard
            label="أصول تحتاج انتباهاً"
            value={formatNumber(critical.length)}
            icon="maintenance"
            tone={critical.length > 0 ? 'warning' : 'success'}
            loading={assetsQuery.isPending}
            footnote="درجة الصحة أقل من 75"
            footnoteTone={critical.length > 0 ? 'warning' : 'success'}
          />
          <KpiCard
            label="أصول بحالة حرجة"
            value={formatNumber(assets.filter((a) => a.healthScore < 50).length)}
            icon="emergency"
            tone={assets.some((a) => a.healthScore < 50) ? 'critical' : 'success'}
            loading={assetsQuery.isPending}
            footnote="تتطلب استبدالاً أو صيانة شاملة"
          />
        </KpiGrid>
      </Section>

      <Section>
        <SplitGrid>
          <Panel
            title="متوسط صحة الأصول لكل منشأة"
            subtitle="يكشف أي منشأة تسحب المتوسط العام للأسفل"
          >
            {facilitiesQuery.isPending ? (
              <SkeletonLines count={5} />
            ) : byFacility.length === 0 ? (
              <StateCard bare title="لا توجد بيانات كافية" />
            ) : (
              <ComparisonBars
                bars={byFacility.map((row) => ({ ...row, display: `${row.value}%` }))}
              />
            )}
          </Panel>

          <Panel title="توزيع درجات الصحة">
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 18 }}>
              <ProgressRing percent={averageHealth} size={150} label="المتوسط العام" />
            </div>
            {bands.length > 0 && (
              <DonutChart
                slices={bands}
                centerValue={formatNumber(assets.length)}
                centerLabel="أصل"
                size={170}
              />
            )}
          </Panel>
        </SplitGrid>
      </Section>

      <Section>
        <Panel
          title="أصول تتطلب متابعة"
          subtitle="مرتبة تصاعدياً حسب درجة الصحة — الأسوأ أولاً"
          flush
        >
          <DataTable
            card={false}
            loading={assetsQuery.isPending}
            rows={critical}
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
                      {facilityName(a.facilityId)} · {a.locationInFacility}
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
                key: 'health',
                header: 'درجة الصحة',
                width: '190px',
                sortValue: (a) => a.healthScore,
                render: (a) => <ProgressBar value={a.healthScore} size="sm" showValue />,
              },
              {
                key: 'band',
                header: 'التقييم',
                render: (a) => {
                  const band = healthBand(a.healthScore)
                  return <Badge tone={band.tone}>{band.label}</Badge>
                },
              },
              {
                key: 'faults',
                header: 'الأعطال',
                numeric: true,
                sortValue: (a) => a.faultCount,
                render: (a) => formatNumber(a.faultCount),
              },
              {
                key: 'last',
                header: 'آخر صيانة',
                sortValue: (a) => a.lastMaintenanceAt ?? '',
                render: (a) => (a.lastMaintenanceAt ? formatDate(a.lastMaintenanceAt) : 'لم تُجرَ'),
              },
              {
                key: 'status',
                header: 'الحالة',
                render: (a) => (
                  <Badge tone={ASSET_STATUS_TONE[a.status]}>{ASSET_STATUS_LABELS[a.status]}</Badge>
                ),
              },
            ]}
            empty={
              <StateCard
                bare
                title="جميع الأصول بحالة جيدة"
                description="لا يوجد أصل درجة صحته أقل من 75."
              />
            }
          />
        </Panel>
      </Section>

      <Section>
        <Panel title="ملخص">
          <p className={shared.hint}>
            يبلغ متوسط صحة الأصول عبر المنصة <strong>{formatPercent(averageHealth)}</strong> عبر{' '}
            <strong>{formatNumber(assets.length)}</strong> أصلاً موزّعة على{' '}
            <strong>{formatNumber(facilitiesQuery.data?.length ?? 0)}</strong> منشآت تشغيلية.
            {critical.length > 0 ? (
              <>
                {' '}
                هناك <strong>{formatNumber(critical.length)}</strong> أصلاً بدرجة صحة أقل من 75
                تتطلب جدولة صيانة وقائية، منها{' '}
                <strong>{formatNumber(stats?.outOfServiceAssets ?? 0)}</strong> أصلاً خارج الخدمة
                حالياً.
              </>
            ) : (
              ' جميع الأصول ضمن النطاق الصحي المقبول ولا تتطلب تدخلاً عاجلاً.'
            )}
          </p>
        </Panel>
      </Section>
    </>
  )
}
