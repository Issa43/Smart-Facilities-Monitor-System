import { useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Truck, X } from 'lucide-react'
import type { MaterialRequest, MaterialRequestStatus } from '@/types'
import {
  MATERIAL_REQUEST_STATUS_LABELS,
  MATERIAL_REQUEST_STATUS_TONE,
  PRIORITY_LABELS,
  PRIORITY_TONE,
} from '@/types'
import { formatDate, formatNumber, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { listMaterialRequests, listProjects, setMaterialRequestStatus } from '@/api/construction'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button, LinkButton } from '@/components/ui/Button/Button'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { ErrorState, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section } from '@/components/ui/Display/Display'

type RequestFilter = MaterialRequestStatus | 'all'

const FILTERS: { value: RequestFilter; label: string }[] = [
  { value: 'all', label: 'الكل' },
  { value: 'pending', label: 'قيد المعالجة' },
  { value: 'approved', label: 'معتمد' },
  { value: 'delivered', label: 'تم التوريد' },
  { value: 'rejected', label: 'مرفوض' },
]

export function MaterialRequestsPage() {
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const { showToast } = useToast()

  const projectsQuery = useQuery({
    queryKey: qk.projects.list(user.id),
    queryFn: () => listProjects(user.id),
  })
  const requestsQuery = useQuery({
    queryKey: qk.materials.requests(),
    queryFn: () => listMaterialRequests(),
  })

  const myProjectIds = new Set(projectsQuery.data?.map((p) => p.id))
  const myRequests = requestsQuery.data?.filter((r) => myProjectIds.has(r.projectId)) ?? []
  const projectName = useCallback(
    (id: string) => projectsQuery.data?.find((p) => p.id === id)?.name ?? '—',
    [projectsQuery.data],
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<
    MaterialRequest,
    RequestFilter
  >(myRequests, {
    searchText: useCallback((r: MaterialRequest) => `${r.materialName} ${r.reason}`, []),
    matchesFilter: useCallback((r: MaterialRequest, v: RequestFilter) => r.status === v, []),
    allValue: 'all',
  })

  const updateStatus = useMutation({
    mutationFn: (input: { id: string; status: MaterialRequestStatus }) =>
      setMaterialRequestStatus(input.id, input.status),
    onSuccess: (request) => {
      queryClient.invalidateQueries({ queryKey: qk.materials.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.construction(user.id) })
      showToast({
        tone: request.status === 'rejected' ? 'critical' : 'success',
        title: `تم تحديث الطلب إلى «${MATERIAL_REQUEST_STATUS_LABELS[request.status]}»`,
        description: request.materialName,
      })
    },
  })

  const counts = FILTERS.map((option) => ({
    ...option,
    count:
      option.value === 'all'
        ? myRequests.length
        : myRequests.filter((r) => r.status === option.value).length,
  }))

  const pending = myRequests.filter((r) => r.status === 'pending')

  if (requestsQuery.isError) return <ErrorState error={requestsQuery.error} />

  return (
    <>
      <PageHeader
        title="طلبات المواد"
        description="دورة الطلب: قيد المعالجة ← معتمد ← تم التوريد. الطلبات المفتوحة تمنع إنهاء المشروع وتحويله لمرحلة التشغيل."
        actions={<LinkButton to="/construction/material-requests/new">+ طلب جديد</LinkButton>}
      />

      <Section>
        <KpiGrid cols={4}>
          <KpiCard
            label="إجمالي الطلبات"
            value={formatNumber(myRequests.length)}
            icon="materialRequests"
            tone="primary"
            loading={requestsQuery.isPending}
          />
          <KpiCard
            label="قيد المعالجة"
            value={formatNumber(pending.length)}
            icon="progress"
            tone={pending.length > 0 ? 'warning' : 'success'}
            loading={requestsQuery.isPending}
            footnote={pending.length > 0 ? 'تتطلب قراراً' : 'لا توجد طلبات معلّقة'}
            footnoteTone={pending.length > 0 ? 'warning' : 'success'}
          />
          <KpiCard
            label="معتمدة"
            value={formatNumber(myRequests.filter((r) => r.status === 'approved').length)}
            icon="quality"
            tone="info"
            loading={requestsQuery.isPending}
            footnote="بانتظار التوريد"
          />
          <KpiCard
            label="تم توريدها"
            value={formatNumber(myRequests.filter((r) => r.status === 'delivered').length)}
            icon="materials"
            tone="success"
            loading={requestsQuery.isPending}
          />
        </KpiGrid>
      </Section>

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput value={query} onChange={setQuery} placeholder="ابحث باسم المادة أو السبب…" />
          <FilterBar
            options={counts}
            value={filter}
            onChange={setFilter}
            label="تصفية الطلبات حسب الحالة"
          />
        </div>
      </Toolbar>

      <DataTable
        loading={requestsQuery.isPending}
        rows={filtered}
        rowKey={(request) => request.id}
        columns={[
          {
            key: 'material',
            header: 'المادة',
            sortValue: (r) => r.materialName,
            render: (r) => (
              <div>
                <div style={{ fontWeight: 700 }}>{r.materialName}</div>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>
                  {projectName(r.projectId)}
                </div>
              </div>
            ),
          },
          {
            key: 'qty',
            header: 'الكمية',
            numeric: true,
            sortValue: (r) => r.requestedQty,
            render: (r) => `${formatNumber(r.requestedQty)} ${r.unit}`,
          },
          { key: 'reason', header: 'سبب الطلب', render: (r) => r.reason },
          {
            key: 'priority',
            header: 'الأولوية',
            sortValue: (r) => r.priority,
            render: (r) => (
              <Badge tone={PRIORITY_TONE[r.priority]}>{PRIORITY_LABELS[r.priority]}</Badge>
            ),
          },
          {
            key: 'created',
            header: 'تاريخ الطلب',
            sortValue: (r) => r.createdAt,
            render: (r) => (
              <span title={formatDate(r.createdAt)}>{formatRelative(r.createdAt)}</span>
            ),
          },
          {
            key: 'status',
            header: 'الحالة',
            sortValue: (r) => r.status,
            render: (r) => (
              <Badge tone={MATERIAL_REQUEST_STATUS_TONE[r.status]}>
                {MATERIAL_REQUEST_STATUS_LABELS[r.status]}
              </Badge>
            ),
          },
          {
            key: 'actions',
            header: 'الإجراء',
            width: '210px',
            render: (r) => {
              const busy = updateStatus.isPending && updateStatus.variables?.id === r.id
              if (r.status === 'pending') {
                return (
                  <div style={{ display: 'flex', gap: 6 }}>
                    <Button
                      size="sm"
                      variant="success"
                      loading={busy && updateStatus.variables?.status === 'approved'}
                      onClick={() => updateStatus.mutate({ id: r.id, status: 'approved' })}
                    >
                      <Check size={13} strokeWidth={2.4} />
                      اعتماد
                    </Button>
                    <Button
                      size="sm"
                      variant="critical"
                      loading={busy && updateStatus.variables?.status === 'rejected'}
                      onClick={() => updateStatus.mutate({ id: r.id, status: 'rejected' })}
                    >
                      <X size={13} strokeWidth={2.4} />
                      رفض
                    </Button>
                  </div>
                )
              }
              if (r.status === 'approved') {
                return (
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={busy}
                    onClick={() => updateStatus.mutate({ id: r.id, status: 'delivered' })}
                  >
                    <Truck size={13} strokeWidth={2} />
                    تأكيد التوريد
                  </Button>
                )
              }
              return <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>—</span>
            },
          },
        ]}
        empty={
          <StateCard
            bare
            title="لا توجد طلبات مطابقة"
            description="أنشئ طلب توريد جديد أو غيّر عوامل التصفية."
          />
        }
      />
    </>
  )
}
