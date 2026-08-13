import { useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, MapPin } from 'lucide-react'
import type { Project, ProjectStatus } from '@/types'
import { FACILITY_TYPE_LABELS, PROJECT_STATUS_LABELS, PROJECT_STATUS_TONE } from '@/types'
import { formatDate, formatNumber, formatPercent } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { listProjects } from '@/api/construction'
import { useCurrentUser } from '@/context/AuthContext'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { EntityCard, EntityGrid } from '@/components/ui/EntityCard/EntityCard'
import { ErrorState, StateCard } from '@/components/ui/Feedback/Feedback'

type StatusFilter = ProjectStatus | 'all'

const FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'الكل' },
  { value: 'in_progress', label: 'قيد التنفيذ' },
  { value: 'planning', label: 'قيد التخطيط' },
  { value: 'on_hold', label: 'متوقف مؤقتاً' },
  { value: 'operational', label: 'مسلّم' },
]

export function ConstructionProjectsPage() {
  const user = useCurrentUser()

  const projectsQuery = useQuery({
    queryKey: qk.projects.list(user.id),
    queryFn: () => listProjects(user.id),
  })

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<Project, StatusFilter>(
    projectsQuery.data,
    {
      searchText: useCallback((p: Project) => `${p.name} ${p.location} ${p.currentStageName}`, []),
      matchesFilter: useCallback((p: Project, value: StatusFilter) => p.status === value, []),
      allValue: 'all',
    },
  )

  const counts = FILTERS.map((option) => ({
    ...option,
    count:
      option.value === 'all'
        ? projectsQuery.data?.length
        : projectsQuery.data?.filter((p) => p.status === option.value).length,
  }))

  if (projectsQuery.isError) return <ErrorState error={projectsQuery.error} />

  return (
    <>
      <PageHeader
        title="المشاريع الإنشائية"
        description={`${formatNumber(projectsQuery.data?.length ?? 0)} مشروع مسند إليك. تظهر هنا المشاريع فور إنشائها من قبل المدير العام.`}
      />

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder="ابحث باسم المشروع أو الموقع…"
          />
          <FilterBar
            options={counts}
            value={filter}
            onChange={setFilter}
            label="تصفية المشاريع حسب الحالة"
          />
        </div>
      </Toolbar>

      {!projectsQuery.isPending && filtered.length === 0 ? (
        <StateCard
          title="لا توجد مشاريع مطابقة"
          description="لم يتم إسناد أي مشروع يطابق البحث الحالي إليك."
        />
      ) : (
        <EntityGrid>
          {filtered.map((project) => (
            <EntityCard
              key={project.id}
              to={`/construction/projects/${project.id}`}
              title={project.name}
              icon="projects"
              badge={
                <Badge tone={PROJECT_STATUS_TONE[project.status]}>
                  {PROJECT_STATUS_LABELS[project.status]}
                </Badge>
              }
              meta={[
                <>
                  <MapPin size={12} /> {project.location}
                </>,
                <>
                  <CalendarDays size={12} /> التسليم: {formatDate(project.expectedEndDate)}
                </>,
                <>{FACILITY_TYPE_LABELS[project.facilityType]}</>,
              ]}
              progress={project.progressPercent}
              footer={
                <>
                  <span>{project.currentStageName}</span>
                  <span style={{ fontWeight: 700, color: 'var(--text)' }}>
                    {formatPercent(project.progressPercent)}
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
