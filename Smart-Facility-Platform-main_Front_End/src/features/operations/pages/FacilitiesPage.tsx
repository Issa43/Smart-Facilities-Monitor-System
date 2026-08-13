import { useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Boxes, CalendarDays, MapPin } from 'lucide-react'
import type { Facility, FacilityStatus } from '@/types'
import { FACILITY_STATUS_LABELS, FACILITY_STATUS_TONE, FACILITY_TYPE_LABELS } from '@/types'
import { formatDate, formatDecimal, formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { listFacilities } from '@/api/operations'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { EntityCard, EntityGrid } from '@/components/ui/EntityCard/EntityCard'
import { ErrorState, StateCard } from '@/components/ui/Feedback/Feedback'

type StatusFilter = FacilityStatus | 'all'

const FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'الكل' },
  { value: 'operational', label: 'تشغيل كامل' },
  { value: 'partial', label: 'تشغيل جزئي' },
  { value: 'under_maintenance', label: 'تحت الصيانة' },
]

export function FacilitiesPage() {
  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<Facility, StatusFilter>(
    facilitiesQuery.data,
    {
      searchText: useCallback((f: Facility) => `${f.name} ${f.location}`, []),
      matchesFilter: useCallback((f: Facility, v: StatusFilter) => f.status === v, []),
      allValue: 'all',
    },
  )

  const counts = FILTERS.map((option) => ({
    ...option,
    count:
      option.value === 'all'
        ? facilitiesQuery.data?.length
        : facilitiesQuery.data?.filter((f) => f.status === option.value).length,
  }))

  if (facilitiesQuery.isError) return <ErrorState error={facilitiesQuery.error} />

  return (
    <>
      <PageHeader
        title="المنشآت"
        description={`${formatNumber(facilitiesQuery.data?.length ?? 0)} منشأة تشغيلية. تظهر المنشأة هنا تلقائياً بعد اعتماد المشروع وتحويله من مرحلة الإنشاء إلى التشغيل.`}
      />

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder="ابحث باسم المنشأة أو الموقع…"
          />
          <FilterBar
            options={counts}
            value={filter}
            onChange={setFilter}
            label="تصفية المنشآت حسب الحالة"
          />
        </div>
      </Toolbar>

      {!facilitiesQuery.isPending && filtered.length === 0 ? (
        <StateCard
          title="لا توجد منشآت مطابقة"
          description="جرّب تعديل كلمة البحث أو اختيار حالة أخرى."
        />
      ) : (
        <EntityGrid>
          {filtered.map((facility) => (
            <EntityCard
              key={facility.id}
              to={`/operations/facilities/${facility.id}`}
              title={facility.name}
              icon="facilities"
              badge={
                <Badge tone={FACILITY_STATUS_TONE[facility.status]}>
                  {FACILITY_STATUS_LABELS[facility.status]}
                </Badge>
              }
              meta={[
                <>
                  <MapPin size={12} /> {facility.location}
                </>,
                <>
                  <Boxes size={12} /> {formatNumber(facility.assetCount)} أصل مُدار
                </>,
                <>
                  <CalendarDays size={12} /> بدء التشغيل: {formatDate(facility.operationStartDate)}
                </>,
              ]}
              progress={facility.uptimePercent}
              progressLabel="الجاهزية التشغيلية"
              footer={
                <>
                  <span>{FACILITY_TYPE_LABELS[facility.type]}</span>
                  <span style={{ fontWeight: 700, color: 'var(--text)' }}>
                    {formatDecimal(facility.uptimePercent)}%
                  </span>
                </>
              }
            />
          ))}
        </EntityGrid>
      )}
    </>
  )
}
