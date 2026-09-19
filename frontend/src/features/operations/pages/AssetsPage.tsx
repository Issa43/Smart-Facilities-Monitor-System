import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import type { AssetStatus } from '@/types'
import { assetCategoryLabel, ASSET_STATUS_LABELS, ASSET_STATUS_TONE } from '@/types'
import { formatDate, formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import {
  createAsset,
  getAssetFilterOptions,
  getAssetMonitoring,
  listAssetsPage,
  listFacilities,
} from '@/api/operations'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { Alert, ErrorState, ProgressBar, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section } from '@/components/ui/Display/Display'

const schema = z
  .object({
    facilityId: z.string().uuid('اختر المنشأة'),
    name: z.string().trim().min(3, 'أدخل اسم الأصل').max(255),
    assetType: z.string().trim().min(1, 'أدخل نوع الأصل').max(100),
    category: z.string().trim().min(1, 'أدخل فئة الأصل').max(100),
    manufacturer: z.string().trim().min(1, 'أدخل الشركة المصنعة').max(100),
    model: z.string().trim().min(1, 'أدخل الطراز').max(100),
    locationInFacility: z.string().trim().min(1, 'أدخل الموقع داخل المنشأة').max(255),
    serialNumber: z.string().trim().min(1, 'أدخل الرقم التسلسلي').max(100),
    installDate: z.string().min(1, 'اختر تاريخ التركيب'),
    commissionDate: z.string(),
    notes: z.string(),
  })
  .refine((values) => !values.commissionDate || values.commissionDate >= values.installDate, {
    path: ['commissionDate'],
    message: 'تاريخ التشغيل لا يمكن أن يسبق تاريخ التركيب',
  })

type AssetFormValues = z.infer<typeof schema>

export function AssetsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [addOpen, setAddOpen] = useState(false)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [facilityId, setFacilityId] = useState('')
  const [status, setStatus] = useState<AssetStatus | ''>('')
  const [assetType, setAssetType] = useState('')
  const [category, setCategory] = useState('')
  const [manufacturer, setManufacturer] = useState('')
  const [location, setLocation] = useState('')
  const [ordering, setOrdering] = useState('name')

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [search])

  const options = {
    page,
    search: debouncedSearch || undefined,
    facilityId: facilityId || undefined,
    status: status || undefined,
    assetType: assetType || undefined,
    category: category || undefined,
    manufacturer: manufacturer || undefined,
    location: location.trim() || undefined,
    ordering,
  }
  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })
  const filterOptionsQuery = useQuery({
    queryKey: [...qk.assets.all, 'filter-options'],
    queryFn: getAssetFilterOptions,
  })
  const assetsQuery = useQuery({
    queryKey: [...qk.assets.all, 'page', options],
    queryFn: () => listAssetsPage(options),
    placeholderData: (previous) => previous,
  })
  const monitoringQuery = useQuery({
    queryKey: [
      ...qk.assets.all,
      'monitoring',
      { ...options, page: undefined, ordering: undefined },
    ],
    queryFn: () => getAssetMonitoring(options),
  })

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
      assetType: '',
      category: '',
      manufacturer: '',
      model: '',
      locationInFacility: '',
      serialNumber: '',
      installDate: '',
      commissionDate: '',
      notes: '',
    },
  })
  const create = useMutation({
    mutationFn: (values: AssetFormValues) => createAsset(values),
    onSuccess: (asset) => {
      queryClient.invalidateQueries({ queryKey: qk.assets.all })
      queryClient.invalidateQueries({ queryKey: qk.facilities.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.operations })
      showToast({ tone: 'success', title: 'تمت إضافة الأصل', description: asset.name })
      setAddOpen(false)
      reset()
    },
  })
  const resetPage = (change: () => void) => {
    change()
    setPage(1)
  }
  const assets = assetsQuery.data?.results ?? []
  const facilityName = (id: string) =>
    facilitiesQuery.data?.find((facility) => facility.id === id)?.name ?? '—'

  if (assetsQuery.isError)
    return <ErrorState error={assetsQuery.error} onRetry={() => assetsQuery.refetch()} />

  return (
    <>
      <PageHeader
        title="إدارة الأصول"
        description={`${formatNumber(assetsQuery.data?.count ?? 0)} أصل ضمن نطاق المنشآت المصرح بها.`}
        actions={<Button onClick={() => setAddOpen(true)}>+ أصل جديد</Button>}
      />
      <Section>
        <KpiGrid cols={4}>
          <KpiCard
            label="إجمالي الأصول"
            value={formatNumber(monitoringQuery.data?.total ?? 0)}
            icon="assets"
            tone="primary"
            loading={monitoringQuery.isPending}
          />
          <KpiCard
            label="أصول تعمل"
            value={formatNumber(monitoringQuery.data?.statusCounts.operational ?? 0)}
            icon="quality"
            tone="success"
            loading={monitoringQuery.isPending}
          />
          <KpiCard
            label="تحت الصيانة"
            value={formatNumber(monitoringQuery.data?.statusCounts.under_maintenance ?? 0)}
            icon="maintenance"
            tone="warning"
            loading={monitoringQuery.isPending}
          />
          <KpiCard
            label="خارج الخدمة"
            value={formatNumber(monitoringQuery.data?.statusCounts.out_of_service ?? 0)}
            icon="corrective"
            tone="critical"
            loading={monitoringQuery.isPending}
          />
        </KpiGrid>
      </Section>
      <Toolbar>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput
            value={search}
            onChange={(value) => resetPage(() => setSearch(value))}
            placeholder="ابحث بالاسم أو النوع أو الرقم أو الموقع…"
          />
          <select
            aria-label="المنشأة"
            value={facilityId}
            onChange={(e) => resetPage(() => setFacilityId(e.target.value))}
          >
            <option value="">كل المنشآت</option>
            {facilitiesQuery.data?.map((facility) => (
              <option key={facility.id} value={facility.id}>
                {facility.name}
              </option>
            ))}
          </select>
          <select
            aria-label="الحالة"
            value={status}
            onChange={(e) => resetPage(() => setStatus(e.target.value as AssetStatus | ''))}
          >
            <option value="">كل الحالات</option>
            {Object.entries(ASSET_STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <select
            aria-label="نوع الأصل"
            value={assetType}
            onChange={(e) => resetPage(() => setAssetType(e.target.value))}
          >
            <option value="">كل أنواع الأصول</option>
            {filterOptionsQuery.data?.assetTypes.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <select
            aria-label="الفئة"
            value={category}
            onChange={(e) => resetPage(() => setCategory(e.target.value))}
          >
            <option value="">كل الفئات</option>
            {filterOptionsQuery.data?.categories.map((value) => (
              <option key={value} value={value}>
                {assetCategoryLabel(value)}
              </option>
            ))}
          </select>
          <select
            aria-label="الشركة المصنعة"
            value={manufacturer}
            onChange={(e) => resetPage(() => setManufacturer(e.target.value))}
          >
            <option value="">كل الشركات المصنعة</option>
            {filterOptionsQuery.data?.manufacturers.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <input
            aria-label="الموقع"
            value={location}
            onChange={(e) => resetPage(() => setLocation(e.target.value))}
            placeholder="الموقع المطابق"
          />
          <select
            aria-label="ترتيب الأصول"
            value={ordering}
            onChange={(e) => resetPage(() => setOrdering(e.target.value))}
          >
            <option value="name">الاسم: تصاعدي</option>
            <option value="-name">الاسم: تنازلي</option>
            <option value="-updated_at">الأحدث تحديثاً</option>
            <option value="-health_score">الصحة: الأعلى</option>
            <option value="health_score">الصحة: الأقل</option>
          </select>
        </div>
      </Toolbar>
      {filterOptionsQuery.isError && (
        <Alert
          tone="critical"
          title="تعذر تحميل خيارات التصفية"
          description={(filterOptionsQuery.error as Error).message}
        />
      )}
      <DataTable
        loading={assetsQuery.isPending}
        rows={assets}
        rowKey={(asset) => asset.id}
        onRowClick={(asset) => navigate(`/operations/assets/${asset.id}`)}
        pagination={
          assetsQuery.data
            ? {
                page: assetsQuery.data.currentPage,
                totalPages: assetsQuery.data.totalPages,
                totalItems: assetsQuery.data.count,
                onPageChange: setPage,
              }
            : undefined
        }
        columns={[
          {
            key: 'name',
            header: 'الأصل',
            render: (asset) => (
              <div>
                <strong>{asset.name}</strong>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {facilityName(asset.facilityId)} · {asset.locationInFacility}
                </div>
              </div>
            ),
          },
          { key: 'type', header: 'نوع الأصل', render: (asset) => asset.assetType || '—' },
          {
            key: 'category',
            header: 'الفئة',
            render: (asset) => <Badge tone="info">{assetCategoryLabel(asset.category)}</Badge>,
          },
          {
            key: 'serial',
            header: 'الرقم التسلسلي',
            render: (asset) => <span className="mono">{asset.serialNumber}</span>,
          },
          {
            key: 'manufacturer',
            header: 'الشركة المصنعة',
            render: (asset) => asset.manufacturer || '—',
          },
          {
            key: 'install',
            header: 'تاريخ التركيب',
            render: (asset) => formatDate(asset.installDate),
          },
          {
            key: 'health',
            header: 'درجة الصحة',
            width: '170px',
            render: (asset) => <ProgressBar value={asset.healthScore} size="sm" showValue />,
          },
          {
            key: 'status',
            header: 'الحالة',
            render: (asset) => (
              <Badge tone={ASSET_STATUS_TONE[asset.status]}>
                {ASSET_STATUS_LABELS[asset.status]}
              </Badge>
            ),
          },
        ]}
        empty={<StateCard bare title="لا توجد أصول مطابقة" />}
      />
      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="إضافة أصل"
        subtitle="يُنشأ الأصل بحالة يعمل؛ تُدار الحالات الأخرى من دورة حياة الأصل."
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setAddOpen(false)}>
              إلغاء
            </Button>
            <Button
              loading={create.isPending}
              onClick={handleSubmit((values) => create.mutate(values))}
            >
              حفظ الأصل
            </Button>
          </>
        }
      >
        <form onSubmit={handleSubmit((values) => create.mutate(values))} noValidate>
          {create.isError && (
            <Alert
              tone="critical"
              title="تعذر حفظ الأصل"
              description={(create.error as Error).message}
            />
          )}
          {facilitiesQuery.isError && (
            <Alert
              tone="critical"
              title="تعذر تحميل المنشآت"
              description={(facilitiesQuery.error as Error).message}
            />
          )}
          {facilitiesQuery.isPending && <Alert title="جارٍ تحميل المنشآت…" />}
          {!facilitiesQuery.isPending &&
            !facilitiesQuery.isError &&
            facilitiesQuery.data?.length === 0 && (
              <Alert tone="warning" title="لا توجد منشآت متاحة ضمن نطاقك" />
            )}
          <FieldRow>
            <Field label="المنشأة" error={errors.facilityId?.message} required>
              {(props) => (
                <select
                  {...props}
                  {...register('facilityId')}
                  disabled={facilitiesQuery.isPending || facilitiesQuery.isError}
                >
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
                <>
                  <input {...props} {...register('category')} list="asset-category-options" />
                  <datalist id="asset-category-options">
                    {filterOptionsQuery.data?.categories.map((value) => (
                      <option key={value} value={value}>
                        {assetCategoryLabel(value)}
                      </option>
                    ))}
                  </datalist>
                </>
              )}
            </Field>
          </FieldRow>
          <Field label="اسم الأصل" error={errors.name?.message} required>
            {(props) => <input {...props} {...register('name')} />}
          </Field>
          <FieldRow>
            <Field label="نوع الأصل" error={errors.assetType?.message} required>
              {(props) => (
                <>
                  <input {...props} {...register('assetType')} list="asset-type-options" />
                  <datalist id="asset-type-options">
                    {filterOptionsQuery.data?.assetTypes.map((value) => (
                      <option key={value} value={value} />
                    ))}
                  </datalist>
                </>
              )}
            </Field>
            <Field label="الشركة المصنعة" error={errors.manufacturer?.message} required>
              {(props) => <input {...props} {...register('manufacturer')} />}
            </Field>
          </FieldRow>
          <Field label="الطراز" error={errors.model?.message} required>
            {(props) => <input {...props} {...register('model')} dir="ltr" />}
          </Field>
          <FieldRow>
            <Field label="الموقع داخل المنشأة" error={errors.locationInFacility?.message} required>
              {(props) => <input {...props} {...register('locationInFacility')} />}
            </Field>
            <Field label="الرقم التسلسلي" error={errors.serialNumber?.message} required>
              {(props) => <input {...props} {...register('serialNumber')} dir="ltr" />}
            </Field>
          </FieldRow>
          <FieldRow>
            <Field label="تاريخ التركيب" error={errors.installDate?.message} required>
              {(props) => <input {...props} {...register('installDate')} type="date" />}
            </Field>
            <Field label="تاريخ التشغيل" error={errors.commissionDate?.message}>
              {(props) => <input {...props} {...register('commissionDate')} type="date" />}
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
