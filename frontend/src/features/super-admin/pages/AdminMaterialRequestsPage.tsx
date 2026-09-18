import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Eye, X } from 'lucide-react'
import type { MaterialRequest, MaterialRequestStatus } from '@/types'
import {
  MATERIAL_REQUEST_STATUS_LABELS,
  MATERIAL_REQUEST_STATUS_TONE,
  PRIORITY_LABELS,
  PRIORITY_TONE,
} from '@/types'
import {
  getMaterialRequest,
  listMaterialRequests,
  setMaterialRequestStatus,
} from '@/api/construction'
import { formatDate, formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { DescriptionList } from '@/components/ui/Display/Display'
import { ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { Modal } from '@/components/ui/Modal/Modal'

export function AdminMaterialRequestsPage() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const requestsQuery = useQuery({
    queryKey: qk.materials.requests(),
    queryFn: () => listMaterialRequests(),
  })
  const detailQuery = useQuery({
    queryKey: ['material-request', selectedId],
    queryFn: () => getMaterialRequest(selectedId!),
    enabled: selectedId !== null,
  })
  const updateStatus = useMutation({
    mutationFn: (input: {
      id: string
      status: Extract<MaterialRequestStatus, 'approved' | 'rejected'>
    }) => setMaterialRequestStatus(input.id, input.status),
    onSuccess: (request) => {
      queryClient.setQueryData(['material-request', request.id], request)
      queryClient.invalidateQueries({ queryKey: qk.materials.requests() })
      showToast({
        tone: request.status === 'rejected' ? 'critical' : 'success',
        title: request.status === 'rejected' ? 'تم رفض طلب المواد' : 'تم اعتماد طلب المواد',
        description: request.materialName,
      })
    },
    onError: (error) => {
      showToast({
        tone: 'critical',
        title: 'تعذّر تحديث طلب المواد',
        description: error instanceof Error ? error.message : undefined,
      })
    },
  })

  const actionButtons = (request: MaterialRequest) => {
    if (request.status !== 'pending') return null
    const busy = updateStatus.isPending && updateStatus.variables?.id === request.id
    return (
      <>
        <Button
          size="sm"
          variant="success"
          loading={busy && updateStatus.variables?.status === 'approved'}
          disabled={updateStatus.isPending}
          onClick={() => updateStatus.mutate({ id: request.id, status: 'approved' })}
        >
          <Check size={14} />
          اعتماد
        </Button>
        <Button
          size="sm"
          variant="critical"
          loading={busy && updateStatus.variables?.status === 'rejected'}
          disabled={updateStatus.isPending}
          onClick={() => updateStatus.mutate({ id: request.id, status: 'rejected' })}
        >
          <X size={14} />
          رفض
        </Button>
      </>
    )
  }

  if (requestsQuery.isError) return <ErrorState error={requestsQuery.error} />

  const selected = detailQuery.data
  return (
    <>
      <PageHeader
        title="طلبات المواد"
        description="مراجعة واعتماد أو رفض طلبات المواد الإنشائية لجميع المشاريع."
      />

      <DataTable
        loading={requestsQuery.isPending}
        rows={requestsQuery.data ?? []}
        rowKey={(request) => request.id}
        columns={[
          {
            key: 'reference',
            header: 'رقم الطلب',
            render: (request) => <span className="mono">{request.id.slice(0, 8)}</span>,
          },
          { key: 'project', header: 'المشروع', render: (request) => request.projectName },
          { key: 'material', header: 'المادة', render: (request) => request.materialName },
          {
            key: 'quantity',
            header: 'الكمية',
            numeric: true,
            render: (request) => `${formatNumber(request.requestedQty)} ${request.unit}`,
          },
          { key: 'requester', header: 'مقدم الطلب', render: (request) => request.requestedByName },
          {
            key: 'date',
            header: 'تاريخ الطلب',
            render: (request) => formatDate(request.createdAt),
          },
          {
            key: 'status',
            header: 'الحالة',
            render: (request) => (
              <Badge tone={MATERIAL_REQUEST_STATUS_TONE[request.status]}>
                {MATERIAL_REQUEST_STATUS_LABELS[request.status]}
              </Badge>
            ),
          },
          {
            key: 'actions',
            header: 'الإجراء',
            width: '250px',
            render: (request) => (
              <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <Button size="sm" variant="ghost" onClick={() => setSelectedId(request.id)}>
                  <Eye size={14} />
                  استعراض
                </Button>
                {actionButtons(request)}
              </span>
            ),
          },
        ]}
        empty={
          <StateCard
            bare
            title="لا توجد طلبات مواد"
            description="ستظهر هنا الطلبات التي ينشئها مديرو الإنشاء."
          />
        }
      />

      <Modal
        open={selectedId !== null}
        onClose={() => setSelectedId(null)}
        title="تفاصيل طلب المواد"
        subtitle={selected ? `الطلب ${selected.id.slice(0, 8)}` : undefined}
        footer={
          selected ? (
            <span style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              {actionButtons(selected)}
              <Button variant="ghost" onClick={() => setSelectedId(null)}>
                إغلاق
              </Button>
            </span>
          ) : undefined
        }
      >
        {detailQuery.isPending ? <SkeletonLines count={5} /> : null}
        {detailQuery.isError ? (
          <ErrorState bare error={detailQuery.error} onRetry={() => detailQuery.refetch()} />
        ) : null}
        {selected ? (
          <DescriptionList
            items={[
              { label: 'المشروع', value: selected.projectName },
              { label: 'المادة', value: selected.materialName },
              { label: 'الكمية', value: `${formatNumber(selected.requestedQty)} ${selected.unit}` },
              { label: 'مقدم الطلب', value: selected.requestedByName },
              { label: 'تاريخ الطلب', value: formatDate(selected.createdAt) },
              {
                label: 'الأولوية',
                value: (
                  <Badge tone={PRIORITY_TONE[selected.priority]}>
                    {PRIORITY_LABELS[selected.priority]}
                  </Badge>
                ),
              },
              {
                label: 'الحالة',
                value: (
                  <Badge tone={MATERIAL_REQUEST_STATUS_TONE[selected.status]}>
                    {MATERIAL_REQUEST_STATUS_LABELS[selected.status]}
                  </Badge>
                ),
              },
              { label: 'سبب الطلب', value: selected.reason },
            ]}
          />
        ) : null}
      </Modal>
    </>
  )
}
