import { useDeferredValue, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { AuditLogEntry } from '@/types'
import { formatDateTime, formatNumber, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { listAuditLogsPage } from '@/api/users'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { Modal } from '@/components/ui/Modal/Modal'
import { ErrorState, StateCard } from '@/components/ui/Feedback/Feedback'
import { Avatar, DescriptionList } from '@/components/ui/Display/Display'
import { auditEntityLabel, presentAuditEntry } from '../auditPresentation'

type EntityFilter = string

export function AdminAuditLogsPage() {
  const [selected, setSelected] = useState<AuditLogEntry | null>(null)
  const [page, setPage] = useState(1)
  const [query, setQueryValue] = useState('')
  const [filter, setFilterValue] = useState<EntityFilter>('all')
  const deferredQuery = useDeferredValue(query)

  const logsQuery = useQuery({
    queryKey: [...qk.auditLogs.all, 'page', page, deferredQuery, filter],
    queryFn: () => listAuditLogsPage({ page, search: deferredQuery, entity: filter }),
    placeholderData: (previous) => previous,
  })

  const setQuery = (value: string) => {
    setQueryValue(value)
    setPage(1)
  }
  const setFilter = (value: EntityFilter) => {
    setFilterValue(value)
    setPage(1)
  }

  const entities = [...new Set((logsQuery.data?.items ?? []).map((entry) => entry.entity))]
  const filters = [
    { value: 'all', label: 'الكل', count: logsQuery.data?.count },
    ...entities.map((entity) => ({
      value: entity,
      label: auditEntityLabel(entity),
    })),
  ]

  if (logsQuery.isError) return <ErrorState error={logsQuery.error} />

  return (
    <>
      <PageHeader
        title="سجل التدقيق"
        description={`${formatNumber(logsQuery.data?.count ?? 0)} عملية مسجّلة. يوثّق النظام كل عملية إنشاء أو تعديل أو حذف مع منفّذها ووقتها وعنوان جهازه.`}
      />

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput value={query} onChange={setQuery} placeholder="ابحث في السجل…" />
          <FilterBar
            options={filters}
            value={filter}
            onChange={setFilter}
            label="تصفية السجل حسب نوع الكيان"
          />
        </div>
      </Toolbar>

      <DataTable
        loading={logsQuery.isPending}
        rows={logsQuery.data?.items ?? []}
        rowKey={(entry) => entry.id}
        onRowClick={setSelected}
        columns={[
          {
            key: 'actor',
            header: 'المنفّذ',
            sortValue: (entry) => entry.actorName ?? '',
            render: (entry) => {
              const actorName = entry.actorName ?? 'مستخدم محذوف'
              return (
                <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <Avatar initials={actorName.slice(0, 2)} size={30} />
                  <span style={{ fontWeight: 700 }}>{actorName}</span>
                </span>
              )
            },
          },
          {
            key: 'action',
            header: 'العملية',
            sortValue: (entry) => entry.action,
            render: (entry) => {
              const presentation = presentAuditEntry(entry)
              return (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 700 }}>{presentation.title}</span>
                  {presentation.technical && (
                    <Badge tone="neutral" plain>
                      تقني
                    </Badge>
                  )}
                </span>
              )
            },
          },
          {
            key: 'entity',
            header: 'الكيان',
            render: (entry) => (
              <Badge tone={presentAuditEntry(entry).technical ? 'neutral' : 'info'}>
                {presentAuditEntry(entry).entityLabel}
              </Badge>
            ),
          },
          {
            key: 'ref',
            header: 'المرجع',
            render: (entry) => presentAuditEntry(entry).reference,
          },
          {
            key: 'ip',
            header: 'عنوان الجهاز',
            render: (entry) => <span className="mono">{entry.ip}</span>,
          },
          {
            key: 'at',
            header: 'الوقت',
            sortValue: (entry) => entry.createdAt,
            render: (entry) => (
              <span title={formatDateTime(entry.createdAt)}>{formatRelative(entry.createdAt)}</span>
            ),
          },
        ]}
        pagination={
          logsQuery.data
            ? {
                page: logsQuery.data.page,
                totalPages: logsQuery.data.totalPages,
                totalItems: logsQuery.data.count,
                onPageChange: setPage,
              }
            : undefined
        }
        empty={
          <StateCard
            bare
            title="لا توجد عمليات مطابقة"
            description="جرّب تعديل كلمة البحث أو اختيار نوع كيان آخر."
          />
        }
      />

      <Modal
        open={selected !== null}
        onClose={() => setSelected(null)}
        title="تفاصيل العملية"
        subtitle={selected ? presentAuditEntry(selected).title : undefined}
        size="sm"
      >
        {selected && (
          <DescriptionList
            single
            items={[
              { label: 'العملية', value: presentAuditEntry(selected).title },
              {
                label: 'المنفّذ',
                value: selected.actorName ?? 'مستخدم محذوف',
              },
              { label: 'نوع الكيان', value: presentAuditEntry(selected).entityLabel },
              { label: 'المرجع', value: presentAuditEntry(selected).reference },
              { label: 'اسم الحدث التقني', value: <span className="mono">{selected.action}</span> },
              { label: 'الكيان التقني', value: <span className="mono">{selected.entity}</span> },
              { label: 'المرجع التقني', value: <span className="mono">{selected.entityRef}</span> },
              { label: 'عنوان الجهاز', value: <span className="mono">{selected.ip}</span> },
              { label: 'التاريخ والوقت', value: formatDateTime(selected.createdAt) },
            ]}
          />
        )}
      </Modal>
    </>
  )
}
