import { useMutation, useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { Download } from 'lucide-react'
import { CAMERA_EVENT_TYPE_LABELS } from '@/types'
import { downloadCameraEventSnapshot, getCameraEvent } from '@/api/aiSecurity'
import { qk } from '@/lib/queryKeys'
import { formatDateTime } from '@/lib/format'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { DescriptionList, Section, SplitGrid } from '@/components/ui/Display/Display'
import { ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { Panel } from '@/components/ui/Panel/Panel'

const box = (value: { x1: number; y1: number; x2: number; y2: number } | null) =>
  value ? `(${value.x1}, ${value.y1}) → (${value.x2}, ${value.y2})` : '—'

export function CameraEventDetailPage() {
  const { eventId = '' } = useParams<{ eventId: string }>()
  const { showToast } = useToast()
  const eventQuery = useQuery({
    queryKey: qk.cameraEvents.detail(eventId),
    queryFn: () => getCameraEvent(eventId),
  })
  const download = useMutation({
    mutationFn: () => downloadCameraEventSnapshot(eventId),
    onError: (error) =>
      showToast({
        tone: 'critical',
        title: 'تعذّر تنزيل اللقطة المحمية',
        description: error instanceof Error ? error.message : undefined,
      }),
  })
  if (eventQuery.isError) return <ErrorState error={eventQuery.error} />
  if (eventQuery.isPending || !eventQuery.data)
    return (
      <Panel>
        <SkeletonLines count={7} />
      </Panel>
    )
  const event = eventQuery.data
  return (
    <>
      <PageHeader
        title={CAMERA_EVENT_TYPE_LABELS[event.eventType]}
        description={`${event.facilityName} — ${event.cameraCode}`}
        crumbs={[{ label: event.id }]}
        actions={
          event.securityAlertId ? (
            <Link to={`/security/alerts/${event.securityAlertId}`}>فتح التنبيه المرتبط</Link>
          ) : undefined
        }
      />
      <Section>
        <SplitGrid>
          <Panel title="عقد الحدث">
            <DescriptionList
              items={[
                { label: 'النوع', value: CAMERA_EVENT_TYPE_LABELS[event.eventType] },
                {
                  label: 'الحالة',
                  value: (
                    <Badge tone={event.securityAlertId ? 'critical' : 'neutral'}>
                      {event.status}
                    </Badge>
                  ),
                },
                { label: 'الكاميرا', value: event.cameraCode },
                { label: 'المنشأة', value: event.facilityName },
                { label: 'ROI', value: event.roiIdentifier ?? '—' },
                { label: 'Track ID', value: event.trackId ?? '—' },
                { label: 'الصنف', value: event.objectClass ?? '—' },
                {
                  label: 'الثقة',
                  value: event.confidence === null ? '—' : `${Math.round(event.confidence * 100)}%`,
                },
                { label: 'وقت الرصد', value: formatDateTime(event.detectedAt) },
                {
                  label: 'وقت التأكيد',
                  value: event.confirmedAt ? formatDateTime(event.confirmedAt) : '—',
                },
                {
                  label: 'المدة',
                  value: event.durationSeconds === null ? '—' : `${event.durationSeconds} ثانية`,
                },
              ]}
            />
          </Panel>
          <Panel title="بيانات النوع">
            <DescriptionList
              items={[
                { label: 'رقم اللوحة', value: event.plateNumber ?? '—' },
                { label: 'نوع المركبة', value: event.vehicleType ?? '—' },
                { label: 'الاتجاه', value: event.direction ?? '—' },
                {
                  label: 'مصرّح',
                  value: event.authorized === null ? '—' : event.authorized ? 'نعم' : 'لا',
                },
                { label: 'نوع العبث', value: event.tamperType ?? '—' },
                {
                  label: 'ضمن وقت مقيّد',
                  value: event.timeRestricted === null ? '—' : event.timeRestricted ? 'نعم' : 'لا',
                },
                { label: 'Bounding box', value: box(event.bbox) },
                { label: 'لوحة المركبة', value: box(event.bboxPlate) },
                { label: 'المركبة', value: box(event.bboxVehicle) },
              ]}
            />
          </Panel>
        </SplitGrid>
      </Section>
      <Section>
        <Panel title="اللقطة المحمية">
          {event.snapshotAvailable ? (
            <StateCard
              bare
              title="اللقطة متاحة عبر وصول محمي فقط"
              action={
                <Button loading={download.isPending} onClick={() => download.mutate()}>
                  <Download size={15} /> تنزيل اللقطة
                </Button>
              }
            />
          ) : (
            <StateCard bare title="لا توجد لقطة متاحة لهذا الحدث" />
          )}
        </Panel>
      </Section>
    </>
  )
}
