import { useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Video, VideoOff } from 'lucide-react'
import { formatNumber, formatPercent } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { listCameras, listSecurityFacilities, type SecurityCamera } from '@/api/security'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { Alert, ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section } from '@/components/ui/Display/Display'
import styles from './Emergency.module.css'

type CameraRow = SecurityCamera & { facilityName: string }
type ZoneFilter = string

export function CameraMonitoringPage() {
  const camerasQuery = useQuery({ queryKey: ['security', 'cameras'], queryFn: listCameras })
  const facilitiesQuery = useQuery({
    queryKey: qk.facilities.list,
    queryFn: listSecurityFacilities,
  })

  const facilityName = useCallback(
    (id: string) => facilitiesQuery.data?.find((facility) => facility.id === id)?.name ?? '—',
    [facilitiesQuery.data],
  )
  const cameras: CameraRow[] = (camerasQuery.data ?? []).map((camera) => ({
    ...camera,
    facilityName: facilityName(camera.facilityId),
  }))

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<CameraRow, ZoneFilter>(
    cameras,
    {
      searchText: useCallback(
        (camera: CameraRow) =>
          `${camera.code} ${camera.name} ${camera.zone} ${camera.facilityName}`,
        [],
      ),
      matchesFilter: useCallback(
        (camera: CameraRow, value: ZoneFilter) =>
          value === 'offline'
            ? !camera.online
            : value === 'online'
              ? camera.online
              : camera.facilityId === value,
        [],
      ),
      allValue: 'all',
    },
  )

  const online = cameras.filter((camera) => camera.online).length
  const offline = cameras.length - online
  const coverage = cameras.length ? Math.round((online / cameras.length) * 100) : 0
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

  if (camerasQuery.isError) return <ErrorState error={camerasQuery.error} />

  return (
    <>
      <PageHeader
        title="مركز مراقبة الكاميرات"
        description="الحالة المسجّلة لشبكة كاميرات المراقبة ضمن المنشآت المصرّح لك بها."
      />

      <Section>
        <KpiGrid cols={4}>
          <KpiCard
            label="إجمالي الكاميرات"
            value={formatNumber(cameras.length)}
            icon="camera"
            tone="primary"
            loading={camerasQuery.isPending}
          />
          <KpiCard
            label="كاميرات متصلة"
            value={formatNumber(online)}
            icon="quality"
            tone="success"
            loading={camerasQuery.isPending}
          />
          <KpiCard
            label="خارج الخدمة"
            value={formatNumber(offline)}
            icon="corrective"
            tone={offline ? 'critical' : 'success'}
            loading={camerasQuery.isPending}
            footnote={offline ? 'تتطلب صيانة' : 'الشبكة كاملة'}
            footnoteTone={offline ? 'critical' : 'success'}
          />
          <KpiCard
            label="نسبة التغطية"
            value={formatPercent(coverage)}
            icon="analytics"
            tone={coverage >= 95 ? 'success' : 'warning'}
            loading={camerasQuery.isPending}
            progress={coverage}
          />
        </KpiGrid>
      </Section>

      {offline > 0 && (
        <Section>
          <Alert
            tone="warning"
            title={`${formatNumber(offline)} كاميرا خارج الخدمة`}
            description="راجع حالة الكاميرات المتأثرة وافتح أمر صيانة عند الحاجة."
          />
        </Section>
      )}

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder="ابحث برمز الكاميرا أو المنطقة…"
          />
          <FilterBar
            options={filters}
            value={filter}
            onChange={setFilter}
            label="تصفية الكاميرات"
          />
        </div>
      </Toolbar>

      {camerasQuery.isPending ? (
        <SkeletonLines count={6} />
      ) : filtered.length === 0 ? (
        <StateCard
          title="لا توجد كاميرات مطابقة"
          description="لا توجد سجلات كاميرات ضمن هذا النطاق أو التصفية."
        />
      ) : (
        <div className={styles.cameraGrid}>
          {filtered.map((camera) => (
            <article key={camera.id} className={styles.camera}>
              <div className={camera.online ? styles.feed : `${styles.feed} ${styles.feedOffline}`}>
                {camera.online && camera.streamAvailable ? (
                  <>
                    <span className={styles.scan} />
                    <Video size={34} strokeWidth={1.6} className={styles.feedIcon} />
                    <span className={styles.recBadge}>
                      <span className={styles.recDot} />
                      إشارة متاحة
                    </span>
                  </>
                ) : (
                  <>
                    <VideoOff size={34} strokeWidth={1.6} className={styles.feedIcon} />
                    <span className={styles.offlineLabel}>
                      {camera.online ? 'البث غير متاح' : 'لا توجد إشارة'}
                    </span>
                  </>
                )}
              </div>
              <div className={styles.cameraBody}>
                <div className={styles.cameraName}>
                  <span className="mono">{camera.code}</span>
                </div>
                <div className={styles.cameraZone}>
                  {camera.name} — {camera.zone}
                </div>
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
