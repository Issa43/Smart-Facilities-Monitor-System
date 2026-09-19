import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { CAMERA_EVENT_TYPE_LABELS, type CameraEventType } from '@/types'
import { listCameraEvents } from '@/api/aiSecurity'
import { qk } from '@/lib/queryKeys'
import { formatDateTime } from '@/lib/format'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { Panel } from '@/components/ui/Panel/Panel'
import { Section } from '@/components/ui/Display/Display'

type EventFilter = CameraEventType | 'all'
const filters: { value: EventFilter; label: string }[] = [
  { value: 'all', label: 'الكل' },
  ...Object.entries(CAMERA_EVENT_TYPE_LABELS).map(([value, label]) => ({
    value: value as CameraEventType,
    label,
  })),
]

export function CameraEventsPage() {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<EventFilter>('all')
  const eventsQuery = useQuery({
    queryKey: qk.cameraEvents.list,
    queryFn: () => listCameraEvents(),
  })
  const events = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase()
    return (eventsQuery.data ?? []).filter(
      (event) =>
        (filter === 'all' || event.eventType === filter) &&
        (!needle ||
          `${event.cameraCode} ${event.facilityName} ${event.roiIdentifier ?? ''} ${event.plateNumber ?? ''}`
            .toLocaleLowerCase()
            .includes(needle)),
    )
  }, [eventsQuery.data, filter, query])

  if (eventsQuery.isError) return <ErrorState error={eventsQuery.error} />
  return (
    <>
      <PageHeader
        title="أحداث الكاميرات"
        description="الأحداث النهائية الواردة من خدمات التحليل الخارجية. واجهة REST هي المصدر المعتمد للبيانات."
      />
      <Toolbar>
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder="ابحث بالكاميرا أو المنشأة أو اللوحة…"
        />
        <FilterBar options={filters} value={filter} onChange={setFilter} label="تصفية نوع الحدث" />
      </Toolbar>
      <Section>
        {eventsQuery.isPending ? (
          <SkeletonLines count={6} />
        ) : events.length === 0 ? (
          <StateCard
            title="لا توجد أحداث كاميرا مطابقة"
            description="لم تُسجّل أحداث نهائية ضمن هذا النطاق بعد."
          />
        ) : (
          <div style={{ display: 'grid', gap: 12 }}>
            {events.map((event) => (
              <Panel
                key={event.id}
                title={
                  <Link to={`/security/events/${event.id}`}>
                    {CAMERA_EVENT_TYPE_LABELS[event.eventType]}
                  </Link>
                }
                actions={
                  <Badge tone={event.securityAlertId ? 'critical' : 'neutral'}>
                    {event.status}
                  </Badge>
                }
              >
                <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
                  <span>
                    <strong>الكاميرا:</strong> {event.cameraCode}
                  </span>
                  <span>
                    <strong>المنشأة:</strong> {event.facilityName}
                  </span>
                  <span>
                    <strong>ROI:</strong> {event.roiIdentifier ?? '—'}
                  </span>
                  <span>
                    <strong>الثقة:</strong>{' '}
                    {event.confidence === null ? '—' : `${Math.round(event.confidence * 100)}%`}
                  </span>
                  <span>
                    <strong>الرصد:</strong> {formatDateTime(event.detectedAt)}
                  </span>
                </div>
              </Panel>
            ))}
          </div>
        )}
      </Section>
    </>
  )
}
