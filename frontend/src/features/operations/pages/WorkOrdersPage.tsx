import { useCallback, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Controller, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import type { MaintenanceType, Priority, WorkOrder, WorkOrderStatus } from '@/types'
import {
  MAINTENANCE_TYPE_LABELS,
  PRIORITY_LABELS,
  PRIORITY_TONE,
  WORK_ORDER_STATUS_LABELS,
  WORK_ORDER_STATUS_TONE,
} from '@/types'
import { formatDate, formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { createWorkOrder, listAssets, listFacilities, listWorkOrders } from '@/api/operations'
import { listUsers } from '@/api/users'
import { useToast } from '@/context/ToastContext'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/ui/SearchableSelect/SearchableSelect'
import { ErrorState, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section } from '@/components/ui/Display/Display'

type StatusFilter = WorkOrderStatus | 'all'

const FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'الكل' },
  { value: 'open', label: 'مفتوح' },
  { value: 'assigned', label: WORK_ORDER_STATUS_LABELS.assigned },
  { value: 'in_progress', label: 'قيد التنفيذ' },
  { value: 'completed', label: 'مكتمل' },
  { value: 'closed', label: WORK_ORDER_STATUS_LABELS.closed },
  { value: 'cancelled', label: 'ملغي' },
]

const schema = z.object({
  assetType: z.string().min(1, 'اختر نوع الأصل'),
  assetId: z.string().min(1, 'اختر الأصل'),
  maintenanceType: z.string().min(1, 'اختر نوع الصيانة'),
  reason: z.string().trim().min(5, 'أدخل سبب الصيانة'),
  description: z.string().trim().min(10, 'أدخل وصفاً لا يقل عن 10 أحرف'),
  priority: z.string().min(1, 'اختر مستوى الأولوية'),
  scheduledDate: z.string().min(1, 'اختر تاريخ التنفيذ المتوقع'),
  assignedToId: z.string(),
  tasks: z.string(),
})

type WorkOrderFormValues = z.infer<typeof schema>

interface WorkOrdersPageProps {
  /** When set, the page shows only that maintenance type (preventive/corrective pages). */
  maintenanceType?: MaintenanceType
  title?: string
  description?: string
}

export function WorkOrdersPage({ maintenanceType, title, description }: WorkOrdersPageProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [addOpen, setAddOpen] = useState(false)

  const ordersQuery = useQuery({ queryKey: qk.workOrders.list(), queryFn: () => listWorkOrders() })
  const assetsQuery = useQuery({ queryKey: qk.assets.list(), queryFn: () => listAssets() })
  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })
  const usersQuery = useQuery({ queryKey: qk.users.all, queryFn: listUsers })

  const scoped = maintenanceType
    ? (ordersQuery.data ?? []).filter((order) => order.maintenanceType === maintenanceType)
    : (ordersQuery.data ?? [])

  const assetName = useCallback(
    (id: string) => assetsQuery.data?.find((a) => a.id === id)?.name ?? '—',
    [assetsQuery.data],
  )
  const facilityName = useCallback(
    (id: string) => facilitiesQuery.data?.find((facility) => facility.id === id)?.name ?? '—',
    [facilitiesQuery.data],
  )
  const userName = useCallback(
    (id: string | null) =>
      id ? (usersQuery.data?.find((u) => u.id === id)?.fullName ?? '—') : 'غير مُسند',
    [usersQuery.data],
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<WorkOrder, StatusFilter>(
    scoped,
    {
      searchText: useCallback((o: WorkOrder) => `${o.reference} ${o.reason} ${o.description}`, []),
      matchesFilter: useCallback((o: WorkOrder, v: StatusFilter) => o.status === v, []),
      allValue: 'all',
    },
  )

  const {
    control,
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<WorkOrderFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      assetType: '',
      assetId: '',
      maintenanceType: maintenanceType ?? 'preventive',
      reason: '',
      description: '',
      priority: 'medium',
      scheduledDate: '',
      assignedToId: '',
      tasks: '',
    },
  })

  const selectedAssetType = watch('assetType')
  const selectedAssetId = watch('assetId')
  const assets = useMemo(() => assetsQuery.data ?? [], [assetsQuery.data])
  const assetTypeOptions = useMemo<SearchableSelectOption[]>(() => {
    const unique = new Map<string, string>()
    for (const asset of assets) {
      const value = asset.assetType?.trim() ?? ''
      const key = value.toLocaleLowerCase()
      if (key && !unique.has(key)) unique.set(key, value)
    }
    return [...unique.values()]
      .sort((left, right) => left.localeCompare(right, 'ar'))
      .map((assetType) => ({ value: assetType, label: assetType }))
  }, [assets])
  const assetOptions = useMemo<SearchableSelectOption[]>(() => {
    const typeKey = selectedAssetType.trim().toLocaleLowerCase()
    return assets
      .filter((asset) => !typeKey || asset.assetType?.trim().toLocaleLowerCase() === typeKey)
      .map((asset) => ({
        value: asset.id,
        label: asset.name,
        description: `${asset.assetType} — ${facilityName(asset.facilityId)}`,
        keywords: `${asset.assetType} ${asset.serialNumber} ${asset.locationInFacility}`,
      }))
  }, [assets, facilityName, selectedAssetType])

  const create = useMutation({
    mutationFn: (values: WorkOrderFormValues) => {
      const asset = assetsQuery.data?.find((a) => a.id === values.assetId)
      return createWorkOrder({
        assetId: values.assetId,
        assetType: values.assetType,
        facilityId: asset?.facilityId ?? '',
        maintenanceType: values.maintenanceType as MaintenanceType,
        reason: values.reason,
        description: values.description,
        priority: values.priority as Priority,
        scheduledDate: new Date(values.scheduledDate).toISOString(),
        assignedToId: values.assignedToId || null,
        tasks: values.tasks
          .split('\n')
          .map((task) => task.trim())
          .filter(Boolean),
      })
    },
    onSuccess: (order) => {
      queryClient.invalidateQueries({ queryKey: qk.workOrders.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.operations })
      showToast({
        tone: 'success',
        title: 'تم إنشاء أمر الصيانة',
        description: `${order.reference} — الحالة: مفتوح`,
      })
      setAddOpen(false)
      reset()
    },
  })

  const counts = FILTERS.map((option) => ({
    ...option,
    count:
      option.value === 'all'
        ? scoped.length
        : scoped.filter((order) => order.status === option.value).length,
  }))

  const now = Date.now()
  const open = scoped.filter((o) => ['open', 'assigned', 'in_progress'].includes(o.status))
  const overdue = open.filter((o) => new Date(o.scheduledDate).getTime() < now)

  if (ordersQuery.isError) return <ErrorState error={ordersQuery.error} />

  return (
    <>
      <PageHeader
        title={title ?? 'أوامر الصيانة'}
        description={
          description ??
          'دورة أمر الصيانة: مفتوح ← قيد التنفيذ ← مكتمل. إغلاق الأمر يحدّث تاريخ آخر صيانة ودرجة صحة الأصل تلقائياً.'
        }
        actions={<Button onClick={() => setAddOpen(true)}>+ أمر صيانة</Button>}
      />

      <Section>
        <KpiGrid cols={4}>
          <KpiCard
            label="إجمالي الأوامر"
            value={formatNumber(scoped.length)}
            icon="maintenance"
            tone="primary"
            loading={ordersQuery.isPending}
          />
          <KpiCard
            label="مفتوحة حالياً"
            value={formatNumber(open.length)}
            icon="workOrders"
            tone={open.length > 0 ? 'warning' : 'success'}
            loading={ordersQuery.isPending}
          />
          <KpiCard
            label="متأخرة عن موعدها"
            value={formatNumber(overdue.length)}
            icon="corrective"
            tone={overdue.length > 0 ? 'critical' : 'success'}
            loading={ordersQuery.isPending}
            footnote={overdue.length > 0 ? 'تجاوزت تاريخ التنفيذ' : 'جميع الأوامر ضمن الجدول'}
            footnoteTone={overdue.length > 0 ? 'critical' : 'success'}
          />
          <KpiCard
            label="مكتملة"
            value={formatNumber(scoped.filter((o) => o.status === 'completed').length)}
            icon="quality"
            tone="success"
            loading={ordersQuery.isPending}
          />
        </KpiGrid>
      </Section>

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput value={query} onChange={setQuery} placeholder="ابحث برقم الأمر أو السبب…" />
          <FilterBar
            options={counts}
            value={filter}
            onChange={setFilter}
            label="تصفية أوامر الصيانة حسب الحالة"
          />
        </div>
      </Toolbar>

      <DataTable
        loading={ordersQuery.isPending}
        rows={filtered}
        rowKey={(order) => order.id}
        onRowClick={(order) => navigate(`/operations/work-orders/${order.id}`)}
        columns={[
          {
            key: 'ref',
            header: 'الأمر',
            sortValue: (o) => o.reference,
            render: (o) => (
              <div>
                <div style={{ fontWeight: 700 }}>{o.reason}</div>
                <div
                  className="mono"
                  style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}
                >
                  {o.reference}
                </div>
              </div>
            ),
          },
          { key: 'asset', header: 'الأصل', render: (o) => assetName(o.assetId) },
          ...(maintenanceType
            ? []
            : [
                {
                  key: 'type',
                  header: 'النوع',
                  render: (o: WorkOrder) => (
                    <Badge tone={o.maintenanceType === 'preventive' ? 'info' : 'warning'}>
                      {MAINTENANCE_TYPE_LABELS[o.maintenanceType]}
                    </Badge>
                  ),
                },
              ]),
          {
            key: 'priority',
            header: 'الأولوية',
            sortValue: (o) => o.priority,
            render: (o) => (
              <Badge tone={PRIORITY_TONE[o.priority]}>{PRIORITY_LABELS[o.priority]}</Badge>
            ),
          },
          {
            key: 'scheduled',
            header: 'موعد التنفيذ',
            sortValue: (o) => o.scheduledDate,
            render: (o) => {
              const late =
                ['open', 'assigned', 'in_progress'].includes(o.status) &&
                new Date(o.scheduledDate).getTime() < now
              return (
                <span
                  style={{
                    color: late ? 'var(--critical-dark)' : undefined,
                    fontWeight: late ? 700 : undefined,
                  }}
                >
                  {formatDate(o.scheduledDate)}
                  {late && ' (متأخر)'}
                </span>
              )
            },
          },
          { key: 'assignee', header: 'المُسند إليه', render: (o) => userName(o.assignedToId) },
          {
            key: 'status',
            header: 'الحالة',
            sortValue: (o) => o.status,
            render: (o) => (
              <Badge tone={WORK_ORDER_STATUS_TONE[o.status]}>
                {WORK_ORDER_STATUS_LABELS[o.status]}
              </Badge>
            ),
          },
        ]}
        empty={<StateCard bare title="لا توجد أوامر صيانة مطابقة" />}
      />

      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="إنشاء أمر صيانة"
        subtitle="يُسجَّل الأمر بحالة «مفتوح» ويظهر فوراً في قائمة الأعمال."
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setAddOpen(false)}>
              إلغاء
            </Button>
            <Button loading={create.isPending} onClick={handleSubmit((v) => create.mutate(v))}>
              إنشاء الأمر
            </Button>
          </>
        }
      >
        <form onSubmit={handleSubmit((v) => create.mutate(v))} noValidate>
          <FieldRow>
            <Field label="نوع الأصل للصيانة" error={errors.assetType?.message} required>
              {(props) => (
                <Controller
                  control={control}
                  name="assetType"
                  render={({ field }) => (
                    <SearchableSelect
                      {...props}
                      value={field.value}
                      onChange={(assetType) => {
                        field.onChange(assetType)
                        const selectedAsset = assets.find((asset) => asset.id === selectedAssetId)
                        if (selectedAsset && selectedAsset.assetType !== assetType) {
                          setValue('assetId', '', { shouldValidate: true })
                        }
                      }}
                      options={assetTypeOptions}
                      placeholder="اكتب للبحث عن نوع أصل…"
                      loading={assetsQuery.isPending}
                      error={assetsQuery.isError}
                      emptyMessage="لا توجد أنواع أصول في المنشآت المعيّنة"
                    />
                  )}
                />
              )}
            </Field>

            <Field label="الأصل" error={errors.assetId?.message} required>
              {(props) => (
                <Controller
                  control={control}
                  name="assetId"
                  render={({ field }) => (
                    <SearchableSelect
                      {...props}
                      value={field.value}
                      onChange={(assetId) => {
                        field.onChange(assetId)
                        const asset = assets.find((candidate) => candidate.id === assetId)
                        if (asset?.assetType && asset.assetType !== selectedAssetType) {
                          setValue('assetType', asset.assetType, { shouldValidate: true })
                        }
                      }}
                      options={assetOptions}
                      placeholder="اكتب اسم الأصل أو رقمه التسلسلي…"
                      loading={assetsQuery.isPending}
                      error={assetsQuery.isError}
                      emptyMessage={
                        selectedAssetType
                          ? 'لا توجد أصول من النوع المحدد'
                          : 'لا توجد أصول في المنشآت المعيّنة'
                      }
                    />
                  )}
                />
              )}
            </Field>
          </FieldRow>

          <FieldRow>
            <Field label="نوع الصيانة" error={errors.maintenanceType?.message} required>
              {(props) => (
                <select {...props} {...register('maintenanceType')}>
                  {Object.entries(MAINTENANCE_TYPE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field label="مستوى الأولوية" error={errors.priority?.message} required>
              {(props) => (
                <select {...props} {...register('priority')}>
                  {Object.entries(PRIORITY_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </FieldRow>

          <Field label="سبب الصيانة" error={errors.reason?.message} required>
            {(props) => (
              <input {...props} {...register('reason')} placeholder="تسرب في دائرة التبريد" />
            )}
          </Field>

          <Field label="وصف العمل المطلوب" error={errors.description?.message} required>
            {(props) => <textarea {...props} {...register('description')} rows={3} />}
          </Field>

          <Field label="بنود التنفيذ" hint="بند واحد في كل سطر">
            {(props) => <textarea {...props} {...register('tasks')} rows={4} />}
          </Field>

          <FieldRow>
            <Field label="تاريخ التنفيذ المتوقع" error={errors.scheduledDate?.message} required>
              {(props) => <input {...props} {...register('scheduledDate')} type="date" />}
            </Field>
            <Field label="إسناد إلى" hint="يمكن الإسناد لاحقاً">
              {(props) => (
                <select {...props} {...register('assignedToId')}>
                  <option value="">غير مُسند</option>
                  {usersQuery.data
                    ?.filter((user) => user.role === 'operations_manager')
                    .map((user) => (
                      <option key={user.id} value={user.id}>
                        {user.fullName}
                      </option>
                    ))}
                </select>
              )}
            </Field>
          </FieldRow>
        </form>
      </Modal>
    </>
  )
}
