import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import type { Fault, FaultStatus, Severity } from '@/types'
import { FAULT_STATUS_LABELS, FAULT_STATUS_TONE, SEVERITY_LABELS, SEVERITY_TONE } from '@/types'
import { formatDateTime, formatNumber, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import {
  createFault,
  listAssets,
  listFacilities,
  listFaults,
  setFaultStatus,
} from '@/api/operations'
import { listUsers } from '@/api/users'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { ErrorState, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section } from '@/components/ui/Display/Display'

type SeverityFilter = Severity | 'all' | 'open'

const FILTERS: { value: SeverityFilter; label: string }[] = [
  { value: 'all', label: 'الكل' },
  { value: 'open', label: 'مفتوحة' },
  { value: 'critical', label: 'حرجة' },
  { value: 'high', label: 'عالية' },
  { value: 'medium', label: 'متوسطة' },
  { value: 'low', label: 'منخفضة' },
]

/** The lifecycle a fault moves through, in order. */
const NEXT_STATUS: Record<FaultStatus, FaultStatus | null> = {
  reported: 'investigating',
  investigating: 'repairing',
  repairing: 'resolved',
  resolved: null,
}

const schema = z.object({
  assetId: z.string().min(1, 'اختر الأصل المتضرر'),
  faultType: z.string().trim().min(3, 'أدخل نوع العطل'),
  description: z.string().trim().min(10, 'أدخل وصفاً لا يقل عن 10 أحرف'),
  severity: z.string().min(1, 'اختر درجة الخطورة'),
  assignedToId: z.string(),
})

type FaultFormValues = z.infer<typeof schema>

export function FaultTrackingPage() {
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [addOpen, setAddOpen] = useState(false)

  const faultsQuery = useQuery({ queryKey: qk.faults.list(), queryFn: () => listFaults() })
  const assetsQuery = useQuery({ queryKey: qk.assets.list(), queryFn: () => listAssets() })
  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })
  const usersQuery = useQuery({ queryKey: qk.users.all, queryFn: listUsers })

  const assetName = useCallback(
    (id: string) => assetsQuery.data?.find((a) => a.id === id)?.name ?? '—',
    [assetsQuery.data],
  )
  const userName = useCallback(
    (id: string | null) =>
      id ? (usersQuery.data?.find((u) => u.id === id)?.fullName ?? '—') : 'غير مُسند',
    [usersQuery.data],
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<Fault, SeverityFilter>(
    faultsQuery.data,
    {
      searchText: useCallback((f: Fault) => `${f.reference} ${f.faultType} ${f.description}`, []),
      matchesFilter: useCallback(
        (f: Fault, v: SeverityFilter) =>
          v === 'open' ? f.status !== 'resolved' : f.severity === v,
        [],
      ),
      allValue: 'all',
    },
  )

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FaultFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      assetId: '',
      faultType: '',
      description: '',
      severity: 'medium',
      assignedToId: user.id,
    },
  })

  const create = useMutation({
    mutationFn: (values: FaultFormValues) => {
      const asset = assetsQuery.data?.find((a) => a.id === values.assetId)
      return createFault({
        assetId: values.assetId,
        facilityId: asset?.facilityId ?? '',
        faultType: values.faultType,
        description: values.description,
        severity: values.severity as Severity,
        assignedToId: values.assignedToId || null,
      })
    },
    onSuccess: (fault) => {
      queryClient.invalidateQueries({ queryKey: qk.faults.all })
      queryClient.invalidateQueries({ queryKey: qk.assets.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.operations })
      showToast({
        tone: 'warning',
        title: 'تم تسجيل العطل',
        description: `${fault.reference} — تم تحديث حالة الأصل تلقائياً.`,
      })
      setAddOpen(false)
      reset()
    },
  })

  const advance = useMutation({
    mutationFn: (input: { id: string; status: FaultStatus }) =>
      setFaultStatus(input.id, input.status),
    onSuccess: (fault) => {
      queryClient.invalidateQueries({ queryKey: qk.faults.all })
      queryClient.invalidateQueries({ queryKey: qk.assets.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.operations })
      showToast({
        tone: fault.status === 'resolved' ? 'success' : 'info',
        title: `تم تحديث العطل إلى «${FAULT_STATUS_LABELS[fault.status]}»`,
        description: fault.status === 'resolved' ? 'تمت إعادة الأصل إلى حالة التشغيل.' : undefined,
      })
    },
  })

  const faults = faultsQuery.data ?? []
  const counts = FILTERS.map((option) => ({
    ...option,
    count:
      option.value === 'all'
        ? faults.length
        : option.value === 'open'
          ? faults.filter((f) => f.status !== 'resolved').length
          : faults.filter((f) => f.severity === option.value).length,
  }))

  const open = faults.filter((f) => f.status !== 'resolved')

  if (faultsQuery.isError) return <ErrorState error={faultsQuery.error} />

  return (
    <>
      <PageHeader
        title="تتبع الأعطال"
        description="تسجيل الأعطال ومتابعتها عبر دورة: تم الإبلاغ ← قيد الفحص ← قيد الإصلاح ← تم الإصلاح. تسجيل عطل يخفض درجة صحة الأصل تلقائياً."
        actions={<Button onClick={() => setAddOpen(true)}>+ تسجيل عطل</Button>}
      />

      <Section>
        <KpiGrid cols={4}>
          <KpiCard
            label="إجمالي الأعطال"
            value={formatNumber(faults.length)}
            icon="faults"
            tone="primary"
            loading={faultsQuery.isPending}
          />
          <KpiCard
            label="أعطال مفتوحة"
            value={formatNumber(open.length)}
            icon="corrective"
            tone={open.length > 0 ? 'warning' : 'success'}
            loading={faultsQuery.isPending}
          />
          <KpiCard
            label="أعطال حرجة مفتوحة"
            value={formatNumber(open.filter((f) => f.severity === 'critical').length)}
            icon="emergency"
            tone={open.some((f) => f.severity === 'critical') ? 'critical' : 'success'}
            loading={faultsQuery.isPending}
            footnote={
              open.some((f) => f.severity === 'critical')
                ? 'تتطلب تدخلاً فورياً'
                : 'لا توجد أعطال حرجة'
            }
            footnoteTone={open.some((f) => f.severity === 'critical') ? 'critical' : 'success'}
          />
          <KpiCard
            label="تم إصلاحها"
            value={formatNumber(faults.filter((f) => f.status === 'resolved').length)}
            icon="quality"
            tone="success"
            loading={faultsQuery.isPending}
          />
        </KpiGrid>
      </Section>

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput value={query} onChange={setQuery} placeholder="ابحث برقم العطل أو نوعه…" />
          <FilterBar options={counts} value={filter} onChange={setFilter} label="تصفية الأعطال" />
        </div>
      </Toolbar>

      <DataTable
        loading={faultsQuery.isPending}
        rows={filtered}
        rowKey={(fault) => fault.id}
        columns={[
          {
            key: 'ref',
            header: 'العطل',
            sortValue: (f) => f.reference,
            render: (f) => (
              <div>
                <div style={{ fontWeight: 700 }}>{f.faultType}</div>
                <div
                  className="mono"
                  style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}
                >
                  {f.reference}
                </div>
              </div>
            ),
          },
          { key: 'asset', header: 'الأصل المتضرر', render: (f) => assetName(f.assetId) },
          { key: 'desc', header: 'الوصف', render: (f) => f.description },
          {
            key: 'cause',
            header: 'السبب الجذري',
            render: (f) =>
              f.rootCause ?? <span style={{ color: 'var(--text-faint)' }}>قيد التحديد</span>,
          },
          {
            key: 'severity',
            header: 'الخطورة',
            sortValue: (f) => f.severity,
            render: (f) => (
              <Badge tone={SEVERITY_TONE[f.severity]}>{SEVERITY_LABELS[f.severity]}</Badge>
            ),
          },
          {
            key: 'discovered',
            header: 'وقت الاكتشاف',
            sortValue: (f) => f.discoveredAt,
            render: (f) => (
              <span title={formatDateTime(f.discoveredAt)}>{formatRelative(f.discoveredAt)}</span>
            ),
          },
          { key: 'assignee', header: 'المُسند إليه', render: (f) => userName(f.assignedToId) },
          {
            key: 'status',
            header: 'الحالة',
            sortValue: (f) => f.status,
            render: (f) => (
              <Badge tone={FAULT_STATUS_TONE[f.status]}>{FAULT_STATUS_LABELS[f.status]}</Badge>
            ),
          },
          {
            key: 'action',
            header: 'الإجراء',
            width: '150px',
            render: (f) => {
              const next = NEXT_STATUS[f.status]
              if (!next)
                return <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>مغلق</span>
              return (
                <Button
                  size="sm"
                  variant={next === 'resolved' ? 'success' : 'ghost'}
                  loading={advance.isPending && advance.variables?.id === f.id}
                  onClick={() => advance.mutate({ id: f.id, status: next })}
                >
                  {FAULT_STATUS_LABELS[next]}
                </Button>
              )
            },
          },
        ]}
        empty={<StateCard bare title="لا توجد أعطال مطابقة" />}
      />

      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="تسجيل عطل"
        subtitle="تسجيل العطل يخفض درجة صحة الأصل ويغيّر حالته تلقائياً حسب درجة الخطورة."
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setAddOpen(false)}>
              إلغاء
            </Button>
            <Button loading={create.isPending} onClick={handleSubmit((v) => create.mutate(v))}>
              تسجيل العطل
            </Button>
          </>
        }
      >
        <form onSubmit={handleSubmit((v) => create.mutate(v))} noValidate>
          <Field label="الأصل المتضرر" error={errors.assetId?.message} required>
            {(props) => (
              <select {...props} {...register('assetId')}>
                <option value="">اختر الأصل…</option>
                {facilitiesQuery.data?.map((facility) => (
                  <optgroup key={facility.id} label={facility.name}>
                    {assetsQuery.data
                      ?.filter((asset) => asset.facilityId === facility.id)
                      .map((asset) => (
                        <option key={asset.id} value={asset.id}>
                          {asset.name}
                        </option>
                      ))}
                  </optgroup>
                ))}
              </select>
            )}
          </Field>

          <FieldRow>
            <Field label="نوع العطل" error={errors.faultType?.message} required>
              {(props) => (
                <input {...props} {...register('faultType')} placeholder="تسرب غاز تبريد" />
              )}
            </Field>
            <Field label="درجة الخطورة" error={errors.severity?.message} required>
              {(props) => (
                <select {...props} {...register('severity')}>
                  {Object.entries(SEVERITY_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </FieldRow>

          <Field label="وصف العطل" error={errors.description?.message} required>
            {(props) => <textarea {...props} {...register('description')} rows={3} />}
          </Field>

          <Field label="إسناد إلى">
            {(props) => (
              <select {...props} {...register('assignedToId')}>
                <option value="">غير مُسند</option>
                {usersQuery.data
                  ?.filter((candidate) => candidate.role === 'operations_manager')
                  .map((candidate) => (
                    <option key={candidate.id} value={candidate.id}>
                      {candidate.fullName}
                    </option>
                  ))}
              </select>
            )}
          </Field>
        </form>
      </Modal>
    </>
  )
}
