import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import type { Asset, AssetCategory, AssetStatus } from '@/types'
import { ASSET_CATEGORY_LABELS, ASSET_STATUS_LABELS, ASSET_STATUS_TONE } from '@/types'
import { formatDate, formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { createAsset, listAssets, listFacilities } from '@/api/operations'
import { useToast } from '@/context/ToastContext'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { ErrorState, ProgressBar, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section } from '@/components/ui/Display/Display'

type StatusFilter = AssetStatus | 'all'

const FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'الكل' },
  { value: 'operational', label: 'يعمل' },
  { value: 'needs_maintenance', label: 'يحتاج صيانة' },
  { value: 'under_maintenance', label: 'تحت الصيانة' },
  { value: 'out_of_service', label: 'خارج الخدمة' },
]

const schema = z.object({
  facilityId: z.string().min(1, 'اختر المنشأة'),
  name: z.string().trim().min(3, 'أدخل اسم الأصل'),
  category: z.string().min(1, 'اختر فئة الأصل'),
  locationInFacility: z.string().trim().min(3, 'أدخل الموقع داخل المنشأة'),
  serialNumber: z.string().trim().min(3, 'أدخل الرقم التسلسلي'),
  installDate: z.string().min(1, 'اختر تاريخ التركيب'),
  commissionDate: z.string().min(1, 'اختر تاريخ التشغيل'),
  status: z.string().min(1, 'اختر الحالة'),
  notes: z.string(),
})

type AssetFormValues = z.infer<typeof schema>

export function AssetsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [addOpen, setAddOpen] = useState(false)

  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })
  const assetsQuery = useQuery({ queryKey: qk.assets.list(), queryFn: () => listAssets() })

  const facilityName = useCallback(
    (id: string) => facilitiesQuery.data?.find((f) => f.id === id)?.name ?? '—',
    [facilitiesQuery.data],
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<Asset, StatusFilter>(
    assetsQuery.data,
    {
      searchText: useCallback(
        (a: Asset) => `${a.name} ${a.serialNumber} ${a.locationInFacility}`,
        [],
      ),
      matchesFilter: useCallback((a: Asset, v: StatusFilter) => a.status === v, []),
      allValue: 'all',
    },
  )

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<AssetFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      facilityId: '',
      name: '',
      category: 'hvac',
      locationInFacility: '',
      serialNumber: '',
      installDate: '',
      commissionDate: '',
      status: 'operational',
      notes: '',
    },
  })

  const create = useMutation({
    mutationFn: (values: AssetFormValues) =>
      createAsset({
        facilityId: values.facilityId,
        name: values.name,
        category: values.category as AssetCategory,
        locationInFacility: values.locationInFacility,
        serialNumber: values.serialNumber,
        installDate: new Date(values.installDate).toISOString(),
        commissionDate: new Date(values.commissionDate).toISOString(),
        status: values.status as AssetStatus,
        notes: values.notes,
      }),
    onSuccess: (asset) => {
      queryClient.invalidateQueries({ queryKey: qk.assets.all })
      queryClient.invalidateQueries({ queryKey: qk.facilities.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.operations })
      showToast({ tone: 'success', title: 'تمت إضافة الأصل', description: asset.name })
      setAddOpen(false)
      reset()
    },
  })

  const assets = assetsQuery.data ?? []
  const counts = FILTERS.map((option) => ({
    ...option,
    count:
      option.value === 'all'
        ? assets.length
        : assets.filter((asset) => asset.status === option.value).length,
  }))

  if (assetsQuery.isError) return <ErrorState error={assetsQuery.error} />

  return (
    <>
      <PageHeader
        title="إدارة الأصول"
        description={`${formatNumber(assets.length)} أصل موزّع على المنشآت التشغيلية — أنظمة التكييف، الكهرباء، السباكة، مكافحة الحريق، المصاعد، والأنظمة الأمنية.`}
        actions={<Button onClick={() => setAddOpen(true)}>+ أصل جديد</Button>}
      />

      <Section>
        <KpiGrid cols={4}>
          <KpiCard
            label="إجمالي الأصول"
            value={formatNumber(assets.length)}
            icon="assets"
            tone="primary"
            loading={assetsQuery.isPending}
          />
          <KpiCard
            label="أصول تعمل"
            value={formatNumber(assets.filter((a) => a.status === 'operational').length)}
            icon="quality"
            tone="success"
            loading={assetsQuery.isPending}
          />
          <KpiCard
            label="تحتاج صيانة"
            value={formatNumber(assets.filter((a) => a.status === 'needs_maintenance').length)}
            icon="maintenance"
            tone="warning"
            loading={assetsQuery.isPending}
          />
          <KpiCard
            label="خارج الخدمة"
            value={formatNumber(assets.filter((a) => a.status === 'out_of_service').length)}
            icon="corrective"
            tone="critical"
            loading={assetsQuery.isPending}
          />
        </KpiGrid>
      </Section>

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder="ابحث بالاسم أو الرقم التسلسلي…"
          />
          <FilterBar
            options={counts}
            value={filter}
            onChange={setFilter}
            label="تصفية الأصول حسب الحالة"
          />
        </div>
      </Toolbar>

      <DataTable
        loading={assetsQuery.isPending}
        rows={filtered}
        rowKey={(asset) => asset.id}
        onRowClick={(asset) => navigate(`/operations/assets/${asset.id}`)}
        columns={[
          {
            key: 'name',
            header: 'الأصل',
            sortValue: (a) => a.name,
            render: (a) => (
              <div>
                <div style={{ fontWeight: 700 }}>{a.name}</div>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>
                  {facilityName(a.facilityId)} · {a.locationInFacility}
                </div>
              </div>
            ),
          },
          {
            key: 'category',
            header: 'الفئة',
            sortValue: (a) => a.category,
            render: (a) => <Badge tone="info">{ASSET_CATEGORY_LABELS[a.category]}</Badge>,
          },
          {
            key: 'serial',
            header: 'الرقم التسلسلي',
            sortValue: (a) => a.serialNumber,
            render: (a) => <span className="mono">{a.serialNumber}</span>,
          },
          {
            key: 'install',
            header: 'تاريخ التركيب',
            sortValue: (a) => a.installDate,
            render: (a) => formatDate(a.installDate),
          },
          {
            key: 'health',
            header: 'درجة الصحة',
            width: '170px',
            sortValue: (a) => a.healthScore,
            render: (a) => <ProgressBar value={a.healthScore} size="sm" showValue />,
          },
          {
            key: 'faults',
            header: 'الأعطال',
            numeric: true,
            sortValue: (a) => a.faultCount,
            render: (a) => formatNumber(a.faultCount),
          },
          {
            key: 'status',
            header: 'الحالة',
            sortValue: (a) => a.status,
            render: (a) => (
              <Badge tone={ASSET_STATUS_TONE[a.status]}>{ASSET_STATUS_LABELS[a.status]}</Badge>
            ),
          },
        ]}
        empty={<StateCard bare title="لا توجد أصول مطابقة" />}
      />

      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="إضافة أصل"
        subtitle="بعد الحفظ يصبح الأصل جاهزاً لإنشاء أوامر الصيانة وتسجيل الأعطال عليه."
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setAddOpen(false)}>
              إلغاء
            </Button>
            <Button loading={create.isPending} onClick={handleSubmit((v) => create.mutate(v))}>
              حفظ الأصل
            </Button>
          </>
        }
      >
        <form onSubmit={handleSubmit((v) => create.mutate(v))} noValidate>
          <FieldRow>
            <Field label="المنشأة" error={errors.facilityId?.message} required>
              {(props) => (
                <select {...props} {...register('facilityId')}>
                  <option value="">اختر المنشأة…</option>
                  {facilitiesQuery.data?.map((facility) => (
                    <option key={facility.id} value={facility.id}>
                      {facility.name}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field label="فئة الأصل" error={errors.category?.message} required>
              {(props) => (
                <select {...props} {...register('category')}>
                  {Object.entries(ASSET_CATEGORY_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </FieldRow>

          <Field label="اسم الأصل" error={errors.name?.message} required>
            {(props) => (
              <input {...props} {...register('name')} placeholder="وحدة تكييف مركزية رئيسية" />
            )}
          </Field>

          <FieldRow>
            <Field label="الموقع داخل المنشأة" error={errors.locationInFacility?.message} required>
              {(props) => (
                <input
                  {...props}
                  {...register('locationInFacility')}
                  placeholder="سطح المبنى — غرفة المكائن"
                />
              )}
            </Field>
            <Field label="الرقم التسلسلي" error={errors.serialNumber?.message} required>
              {(props) => (
                <input
                  {...props}
                  {...register('serialNumber')}
                  dir="ltr"
                  placeholder="HVAC-JED-3301"
                />
              )}
            </Field>
          </FieldRow>

          <FieldRow cols={3}>
            <Field label="تاريخ التركيب" error={errors.installDate?.message} required>
              {(props) => <input {...props} {...register('installDate')} type="date" />}
            </Field>
            <Field label="تاريخ التشغيل" error={errors.commissionDate?.message} required>
              {(props) => <input {...props} {...register('commissionDate')} type="date" />}
            </Field>
            <Field label="الحالة" error={errors.status?.message} required>
              {(props) => (
                <select {...props} {...register('status')}>
                  {Object.entries(ASSET_STATUS_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </FieldRow>

          <Field label="ملاحظات">
            {(props) => <textarea {...props} {...register('notes')} rows={3} />}
          </Field>
        </form>
      </Modal>
    </>
  )
}
