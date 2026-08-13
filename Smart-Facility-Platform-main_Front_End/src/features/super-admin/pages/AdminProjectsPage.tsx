import { useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { MapPin, UserCog } from 'lucide-react'
import type { Project, ProjectStatus } from '@/types'
import { FACILITY_TYPE_LABELS, PROJECT_STATUS_LABELS, PROJECT_STATUS_TONE } from '@/types'
import { formatDate, formatNumber, formatPercent } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { listProjects } from '@/api/construction'
import { listUsers } from '@/api/users'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { LinkButton } from '@/components/ui/Button/Button'
import { FilterBar, SearchInput, Toolbar, ViewToggle } from '@/components/ui/Controls/Controls'
import { DataTable, type Column } from '@/components/ui/DataTable/DataTable'
import { EntityCard, EntityGrid } from '@/components/ui/EntityCard/EntityCard'
import { ErrorState, ProgressBar, StateCard } from '@/components/ui/Feedback/Feedback'
import { useViewMode } from '@/hooks/useViewMode'

type StatusFilter = ProjectStatus | 'all'

const FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'الكل' },
  { value: 'in_progress', label: 'قيد التنفيذ' },
  { value: 'planning', label: 'قيد التخطيط' },
  { value: 'on_hold', label: 'متوقف مؤقتاً' },
  { value: 'operational', label: 'قيد التشغيل' },
]

export function AdminProjectsPage() {
  const navigate = useNavigate()
  const [view, setView] = useViewMode('admin-projects')

  const projectsQuery = useQuery({ queryKey: qk.projects.list(), queryFn: () => listProjects() })
  const usersQuery = useQuery({ queryKey: qk.users.all, queryFn: listUsers })

  const managerName = useCallback(
    (id: string) => usersQuery.data?.find((user) => user.id === id)?.fullName ?? '—',
    [usersQuery.data],
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<Project, StatusFilter>(
    projectsQuery.data,
    {
      searchText: useCallback(
        (project: Project) => `${project.name} ${project.location} ${project.currentStageName}`,
        [],
      ),
      matchesFilter: useCallback(
        (project: Project, value: StatusFilter) => project.status === value,
        [],
      ),
      allValue: 'all',
    },
  )

  const counts = FILTERS.map((option) => ({
    ...option,
    count:
      option.value === 'all'
        ? projectsQuery.data?.length
        : projectsQuery.data?.filter((project) => project.status === option.value).length,
  }))

  const columns: Column<Project>[] = [
    {
      key: 'name',
      header: 'المشروع',
      sortValue: (project) => project.name,
      render: (project) => (
        <div>
          <div style={{ fontWeight: 700 }}>{project.name}</div>
          <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>
            {FACILITY_TYPE_LABELS[project.facilityType]} · {project.location}
          </div>
        </div>
      ),
    },
    {
      key: 'manager',
      header: 'مدير الإنشاءات',
      sortValue: (project) => managerName(project.constructionManagerId),
      render: (project) => managerName(project.constructionManagerId),
    },
    {
      key: 'progress',
      header: 'نسبة الإنجاز',
      width: '190px',
      sortValue: (project) => project.progressPercent,
      render: (project) => <ProgressBar value={project.progressPercent} size="sm" showValue />,
    },
    {
      key: 'stage',
      header: 'المرحلة الحالية',
      render: (project) => project.currentStageName,
    },
    {
      key: 'end',
      header: 'الانتهاء المتوقع',
      sortValue: (project) => project.expectedEndDate,
      render: (project) => formatDate(project.expectedEndDate),
    },
    {
      key: 'status',
      header: 'الحالة',
      sortValue: (project) => project.status,
      render: (project) => (
        <Badge tone={PROJECT_STATUS_TONE[project.status]}>
          {PROJECT_STATUS_LABELS[project.status]}
        </Badge>
      ),
    },
  ]

  if (projectsQuery.isError) return <ErrorState error={projectsQuery.error} />

  return (
    <>
      <PageHeader
        title="المشاريع"
        description={`${formatNumber(projectsQuery.data?.length ?? 0)} مشروع مسجّل في المنصة، من مرحلة التخطيط وحتى التشغيل.`}
        actions={<LinkButton to="/admin/projects/new">+ مشروع جديد</LinkButton>}
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
        <ViewToggle value={view} onChange={setView} />
      </Toolbar>

      {!projectsQuery.isPending && filtered.length === 0 ? (
        <StateCard
          title="لا توجد مشاريع مطابقة"
          description="جرّب تعديل كلمة البحث أو اختيار حالة أخرى من عوامل التصفية."
        />
      ) : view === 'list' ? (
        <DataTable
          columns={columns}
          rows={filtered}
          rowKey={(project) => project.id}
          onRowClick={(project) => navigate(`/admin/projects/${project.id}`)}
          loading={projectsQuery.isPending}
        />
      ) : (
        <EntityGrid>
          {filtered.map((project) => (
            <EntityCard
              key={project.id}
              to={`/admin/projects/${project.id}`}
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
                  <UserCog size={12} /> {managerName(project.constructionManagerId)}
                </>,
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
