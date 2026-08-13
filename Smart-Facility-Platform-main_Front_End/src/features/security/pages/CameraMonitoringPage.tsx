import { useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Video, VideoOff } from 'lucide-react'
import { formatNumber, formatPercent } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { listAssets, listFacilities } from '@/api/operations'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { Alert, ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section } from '@/components/ui/Display/Display'
import styles from './Emergency.module.css'

interface Camera {
  id: string
  name: string
  zone: string
  facilityId: string
  facilityName: string
  online: boolean
}

/**
 * Cameras are derived from the security-category assets in each facility rather
 * than stored separately: the CCTV system *is* an asset the operations manager
 * maintains, and inventing a parallel camera table would let the two disagree
 * about how many cameras exist or whether they are working.
 */
function buildCameras(
  assets: { id: string; name: string; facilityId: string; status: string; category: string }[],
  facilityName: (id: string) => string,
): Camera[] {
  const zones = [
    'المدخل الرئيسي',
    'الممر الشرقي',
    'المواقف',
    'منطقة الخدمات',
    'المخارج الطارئة',
    'السطح',
  ]

  return assets
    .filter((asset) => asset.category === 'security')
    .flatMap((asset, assetIndex) =>
      // Each security system stands for a small bank of cameras.
      Array.from({ length: 4 }, (_, index) => ({
        id: `${asset.id}-cam-${index}`,
        name: `CAM-${String(assetIndex * 4 + index + 1).padStart(2, '0')}`,
        zone: zones[(assetIndex + index) % zones.length] as string,
        facilityId: asset.facilityId,
        facilityName: facilityName(asset.facilityId),
        // Only the last camera of a degraded system is shown offline.
        online: asset.status === 'operational' || index < 3,
      })),
    )
}

type ZoneFilter = string

export function CameraMonitoringPage() {
  const assetsQuery = useQuery({ queryKey: qk.assets.list(), queryFn: () => listAssets() })
  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })

  const facilityName = useCallback(
    (id: string) => facilitiesQuery.data?.find((f) => f.id === id)?.name ?? '—',
    [facilitiesQuery.data],
  )

  const cameras = useMemo(
    () => buildCameras(assetsQuery.data ?? [], facilityName),
    [assetsQuery.data, facilityName],
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<Camera, ZoneFilter>(
    cameras,
    {
      searchText: useCallback((c: Camera) => `${c.name} ${c.zone} ${c.facilityName}`, []),
      matchesFilter: useCallback(
        (c: Camera, value: ZoneFilter) =>
          value === 'offline' ? !c.online : value === 'online' ? c.online : c.facilityId === value,
        [],
      ),
      allValue: 'all',
    },
  )

  const online = cameras.filter((camera) => camera.online).length
  const offline = cameras.length - online
  const coverage = cameras.length === 0 ? 0 : Math.round((online / cameras.length) * 100)

  const filters = [
    { value: 'all', label: 'الكل', count: cameras.length },
    { value: 'online', label: 'متصلة', count: online },
    { value: 'offline', label: 'خارج الخدمة', count: offline },
    ...(facilitiesQuery.data ?? [])
      .map((facility) => ({
        value: facility.id,
        label: facility.name,
        count: cameras.filter((camera) => camera.facilityId === facility.id).length,
      }))
      .filter((option) => option.count > 0),
  ]

  if (assetsQuery.isError) return <ErrorState error={assetsQuery.error} />

  return (
    <>
      <PageHeader
        title="مركز مراقبة الكاميرات"
        description="حالة شبكة كاميرات المراقبة عبر المنشآت. الكاميرات مشتقّة من أنظمة المراقبة المسجّلة كأصول تشغيلية."
      />

      <Section>
        <KpiGrid cols={4}>
          <KpiCard
            label="إجمالي الكاميرات"
            value={formatNumber(cameras.length)}
            icon="camera"
            tone="primary"
            loading={assetsQuery.isPending}
          />
          <KpiCard
            label="كاميرات متصلة"
            value={formatNumber(online)}
            icon="quality"
            tone="success"
            loading={assetsQuery.isPending}
          />
          <KpiCard
            label="خارج الخدمة"
            value={formatNumber(offline)}
            icon="corrective"
            tone={offline > 0 ? 'critical' : 'success'}
            loading={assetsQuery.isPending}
            footnote={offline > 0 ? 'تتطلب صيانة' : 'الشبكة كاملة'}
            footnoteTone={offline > 0 ? 'critical' : 'success'}
          />
          <KpiCard
            label="نسبة التغطية"
            value={formatPercent(coverage)}
            icon="analytics"
            tone={coverage >= 95 ? 'success' : 'warning'}
            loading={assetsQuery.isPending}
            progress={coverage}
          />
        </KpiGrid>
      </Section>

      {offline > 0 && (
        <Section>
          <Alert
            tone="warning"
            title={`${formatNumber(offline)} كاميرا خارج الخدمة`}
            description="مناطق التغطية المتأثرة تحتاج إلى صيانة. أبلغ مدير التشغيل لفتح أمر صيانة على نظام المراقبة المعني."
          />
        </Section>
      )}

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder="ابحث برقم الكاميرا أو المنطقة…"
          />
          <FilterBar
            options={filters}
            value={filter}
            onChange={setFilter}
            label="تصفية الكاميرات"
          />
        </div>
      </Toolbar>

      {assetsQuery.isPending ? (
        <SkeletonLines count={6} />
      ) : filtered.length === 0 ? (
        <StateCard title="لا توجد كاميرات مطابقة" description="جرّب تعديل البحث أو التصفية." />
      ) : (
        <div className={styles.cameraGrid}>
          {filtered.map((camera) => (
            <article key={camera.id} className={styles.camera}>
              <div className={camera.online ? styles.feed : `${styles.feed} ${styles.feedOffline}`}>
                {camera.online ? (
                  <>
                    <span className={styles.scan} />
                    <Video size={34} strokeWidth={1.6} className={styles.feedIcon} />
                    <span className={styles.recBadge}>
                      <span className={styles.recDot} />
                      تسجيل مباشر
                    </span>
                  </>
                ) : (
                  <>
                    <VideoOff size={34} strokeWidth={1.6} className={styles.feedIcon} />
                    <span className={styles.offlineLabel}>لا توجد إشارة</span>
                  </>
                )}
              </div>

              <div className={styles.cameraBody}>
                <div className={styles.cameraName}>
                  <span className="mono">{camera.name}</span>
                </div>
                <div className={styles.cameraZone}>{camera.zone}</div>
                <div className={styles.cameraFoot}>
                  <span>{camera.facilityName}</span>
                  <Badge tone={camera.online ? 'success' : 'critical'} live={camera.online}>
                    {camera.online ? 'متصلة' : 'خارج الخدمة'}
                  </Badge>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  )
}
