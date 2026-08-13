import { useCallback, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { AuditLogEntry } from '@/types'
import { formatDateTime, formatNumber, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { listAuditLogs, listUsers } from '@/api/users'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { Modal } from '@/components/ui/Modal/Modal'
import { ErrorState, StateCard } from '@/components/ui/Feedback/Feedback'
import { Avatar, DescriptionList } from '@/components/ui/Display/Display'

type EntityFilter = string

export function AdminAuditLogsPage() {
  const [selected, setSelected] = useState<AuditLogEntry | null>(null)

  const logsQuery = useQuery({ queryKey: qk.auditLogs.all, queryFn: listAuditLogs })
  const usersQuery = useQuery({ queryKey: qk.users.all, queryFn: listUsers })

  const actor = useCallback(
    (id: string) => usersQuery.data?.find((user) => user.id === id),
    [usersQuery.data],
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<
    AuditLogEntry,
    EntityFilter
  >(logsQuery.data, {
    searchText: useCallback(
      (entry: AuditLogEntry) => `${entry.action} ${entry.entity} ${entry.entityRef} ${entry.ip}`,
      [],
    ),
    matchesFilter: useCallback(
      (entry: AuditLogEntry, value: EntityFilter) => entry.entity === value,
      [],
    ),
    allValue: 'all',
  })

  const entities = [...new Set((logsQuery.data ?? []).map((entry) => entry.entity))]
  const filters = [
    { value: 'all', label: 'الكل', count: logsQuery.data?.length },
    ...entities.map((entity) => ({
      value: entity,
      label: entity,
      count: logsQuery.data?.filter((entry) => entry.entity === entity).length,
    })),
  ]

  const sorted = filtered.slice().sort((a, b) => b.createdAt.localeCompare(a.createdAt))

  if (logsQuery.isError) return <ErrorState error={logsQuery.error} />

  return (
    <>
      <PageHeader
        title="سجل التدقيق"
        description={`${formatNumber(logsQuery.data?.length ?? 0)} عملية مسجّلة. يوثّق النظام كل عملية إنشاء أو تعديل أو حذف مع منفّذها ووقتها وعنوان جهازه.`}
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
        rows={sorted}
        rowKey={(entry) => entry.id}
        onRowClick={setSelected}
        columns={[
          {
            key: 'actor',
            header: 'المنفّذ',
            sortValue: (entry) => actor(entry.actorId)?.fullName ?? '',
            render: (entry) => {
              const user = actor(entry.actorId)
              return (
                <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <Avatar initials={user?.initials ?? '؟'} size={30} />
                  <span style={{ fontWeight: 700 }}>{user?.fullName ?? 'مستخدم محذوف'}</span>
                </span>
              )
            },
          },
          {
            key: 'action',
            header: 'العملية',
            sortValue: (entry) => entry.action,
            render: (entry) => entry.action,
          },
          {
            key: 'entity',
            header: 'الكيان',
            render: (entry) => <Badge tone="info">{entry.entity}</Badge>,
          },
          {
            key: 'ref',
            header: 'المرجع',
            render: (entry) => <span className="mono">{entry.entityRef}</span>,
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
        subtitle={selected?.action}
        size="sm"
      >
        {selected && (
          <DescriptionList
            single
            items={[
              { label: 'العملية', value: selected.action },
              {
                label: 'المنفّذ',
                value: actor(selected.actorId)?.fullName ?? 'مستخدم محذوف',
              },
              { label: 'نوع الكيان', value: selected.entity },
              { label: 'المرجع', value: <span className="mono">{selected.entityRef}</span> },
              { label: 'عنوان الجهاز', value: <span className="mono">{selected.ip}</span> },
              { label: 'التاريخ والوقت', value: formatDateTime(selected.createdAt) },
            ]}
          />
        )}
      </Modal>
    </>
  )
}
