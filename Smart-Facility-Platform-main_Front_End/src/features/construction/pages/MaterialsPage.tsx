import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import type { Material } from '@/types'
import { formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { createMaterial, listMaterials, listProjects } from '@/api/construction'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button, LinkButton } from '@/components/ui/Button/Button'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { Alert, ErrorState, ProgressBar, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section } from '@/components/ui/Display/Display'

type StockFilter = 'all' | 'low' | 'ok'

const schema = z.object({
  projectId: z.string().min(1, 'اختر المشروع'),
  name: z.string().trim().min(2, 'أدخل اسم المادة'),
  unit: z.string().trim().min(1, 'أدخل وحدة القياس'),
  requiredQty: z.coerce.number().positive('الكمية المطلوبة يجب أن تكون أكبر من صفر'),
  usedQty: z.coerce.number().min(0, 'الكمية المستخدمة لا يمكن أن تكون سالبة'),
  minStockThreshold: z.coerce.number().min(0, 'الحد الأدنى لا يمكن أن يكون سالباً'),
})

type MaterialFormValues = z.input<typeof schema>

export function MaterialsPage() {
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [addOpen, setAddOpen] = useState(false)

  const projectsQuery = useQuery({
    queryKey: qk.projects.list(user.id),
    queryFn: () => listProjects(user.id),
  })
  const materialsQuery = useQuery({
    queryKey: qk.materials.byProject(),
    queryFn: () => listMaterials(),
  })

  const myProjectIds = new Set(projectsQuery.data?.map((p) => p.id))
  const myMaterials = materialsQuery.data?.filter((m) => myProjectIds.has(m.projectId)) ?? []
  const projectName = useCallback(
    (id: string) => projectsQuery.data?.find((p) => p.id === id)?.name ?? '—',
    [projectsQuery.data],
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<Material, StockFilter>(
    myMaterials,
    {
      searchText: useCallback((m: Material) => `${m.name} ${m.unit}`, []),
      matchesFilter: useCallback(
        (m: Material, value: StockFilter) =>
          value === 'low'
            ? m.remainingQty < m.minStockThreshold
            : m.remainingQty >= m.minStockThreshold,
        [],
      ),
      allValue: 'all',
    },
  )

  const lowStock = myMaterials.filter((m) => m.remainingQty < m.minStockThreshold)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<MaterialFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      projectId: '',
      name: '',
      unit: '',
      requiredQty: 0,
      usedQty: 0,
      minStockThreshold: 0,
    },
  })

  const create = useMutation({
    mutationFn: (values: MaterialFormValues) =>
      createMaterial({
        projectId: values.projectId,
        name: values.name,
        unit: values.unit,
        requiredQty: Number(values.requiredQty),
        usedQty: Number(values.usedQty),
        minStockThreshold: Number(values.minStockThreshold),
      }),
    onSuccess: (material) => {
      queryClient.invalidateQueries({ queryKey: qk.materials.all })
      queryClient.invalidateQueries({ queryKey: qk.notifications.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.construction(user.id) })
      showToast({ tone: 'success', title: 'تمت إضافة المادة', description: material.name })
      setAddOpen(false)
      reset()
    },
  })

  const filters = [
    { value: 'all' as StockFilter, label: 'الكل', count: myMaterials.length },
    { value: 'low' as StockFilter, label: 'تحت الحد الأدنى', count: lowStock.length },
    { value: 'ok' as StockFilter, label: 'ضمن الحد', count: myMaterials.length - lowStock.length },
  ]

  if (materialsQuery.isError) return <ErrorState error={materialsQuery.error} />

  return (
    <>
      <PageHeader
        title="إدارة المواد"
        description="متابعة الكميات المطلوبة والمستخدمة والمتبقية لكل مادة. عند انخفاض الكمية عن الحد الأدنى يُنشئ النظام تنبيهاً تلقائياً."
        actions={
          <>
            <LinkButton to="/construction/material-requests/new" variant="ghost">
              طلب توريد
            </LinkButton>
            <Button onClick={() => setAddOpen(true)}>+ مادة جديدة</Button>
          </>
        }
      />

      <Section>
        <KpiGrid cols={3}>
          <KpiCard
            label="إجمالي المواد"
            value={formatNumber(myMaterials.length)}
            icon="materials"
            tone="primary"
            loading={materialsQuery.isPending}
          />
          <KpiCard
            label="تحت الحد الأدنى"
            value={formatNumber(lowStock.length)}
            icon="corrective"
            tone={lowStock.length > 0 ? 'critical' : 'success'}
            loading={materialsQuery.isPending}
            footnote={lowStock.length > 0 ? 'يتطلب طلب توريد عاجل' : 'جميع المواد ضمن الحدود'}
            footnoteTone={lowStock.length > 0 ? 'critical' : 'success'}
          />
          <KpiCard
            label="متوسط الاستهلاك"
            value={
              myMaterials.length === 0
                ? '—'
                : `${Math.round(
                    (myMaterials.reduce((sum, m) => sum + m.usedQty / (m.requiredQty || 1), 0) /
                      myMaterials.length) *
                      100,
                  )}%`
            }
            icon="progress"
            tone="info"
            loading={materialsQuery.isPending}
            footnote="من الكميات المطلوبة"
          />
        </KpiGrid>
      </Section>

      {lowStock.length > 0 && (
        <Section>
          <Alert
            tone="warning"
            title={`${formatNumber(lowStock.length)} مادة تحت الحد الأدنى للمخزون`}
            description={`${lowStock.map((m) => m.name).join('، ')} — يُنصح بإنشاء طلب توريد قبل توقف الأعمال.`}
          />
        </Section>
      )}

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput value={query} onChange={setQuery} placeholder="ابحث باسم المادة…" />
          <FilterBar
            options={filters}
            value={filter}
            onChange={setFilter}
            label="تصفية المواد حسب حالة المخزون"
          />
        </div>
      </Toolbar>

      <DataTable
        loading={materialsQuery.isPending}
        rows={filtered}
        rowKey={(material) => material.id}
        columns={[
          {
            key: 'name',
            header: 'المادة',
            sortValue: (m) => m.name,
            render: (m) => (
              <div>
                <div style={{ fontWeight: 700 }}>{m.name}</div>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>
                  {projectName(m.projectId)}
                </div>
              </div>
            ),
          },
          { key: 'unit', header: 'الوحدة', render: (m) => m.unit },
          {
            key: 'required',
            header: 'المطلوبة',
            numeric: true,
            sortValue: (m) => m.requiredQty,
            render: (m) => formatNumber(m.requiredQty),
          },
          {
            key: 'used',
            header: 'المستخدمة',
            numeric: true,
            sortValue: (m) => m.usedQty,
            render: (m) => formatNumber(m.usedQty),
          },
          {
            key: 'remaining',
            header: 'المتبقية',
            numeric: true,
            sortValue: (m) => m.remainingQty,
            render: (m) => (
              <span
                style={{
                  fontWeight: 700,
                  color:
                    m.remainingQty < m.minStockThreshold ? 'var(--critical-dark)' : 'var(--text)',
                }}
              >
                {formatNumber(m.remainingQty)}
              </span>
            ),
          },
          {
            key: 'threshold',
            header: 'الحد الأدنى',
            numeric: true,
            render: (m) => formatNumber(m.minStockThreshold),
          },
          {
            key: 'consumption',
            header: 'نسبة الاستهلاك',
            width: '170px',
            sortValue: (m) => m.usedQty / (m.requiredQty || 1),
            render: (m) => (
              <ProgressBar
                value={Math.round((m.usedQty / (m.requiredQty || 1)) * 100)}
                size="sm"
                showValue
                tone="info"
              />
            ),
          },
          {
            key: 'status',
            header: 'الحالة',
            render: (m) =>
              m.remainingQty < m.minStockThreshold ? (
                <Badge tone="critical">تحت الحد</Badge>
              ) : (
                <Badge tone="success">سليم</Badge>
              ),
          },
        ]}
        empty={<StateCard bare title="لا توجد مواد مطابقة" />}
      />

      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="إضافة مادة"
        subtitle="الكمية المتبقية تُحتسب تلقائياً من الفرق بين المطلوبة والمستخدمة."
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setAddOpen(false)}>
              إلغاء
            </Button>
            <Button loading={create.isPending} onClick={handleSubmit((v) => create.mutate(v))}>
              حفظ المادة
            </Button>
          </>
        }
      >
        <form onSubmit={handleSubmit((v) => create.mutate(v))} noValidate>
          <Field label="المشروع" error={errors.projectId?.message} required>
            {(props) => (
              <select {...props} {...register('projectId')}>
                <option value="">اختر المشروع…</option>
                {projectsQuery.data
                  ?.filter((p) => p.status !== 'operational')
                  .map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
              </select>
            )}
          </Field>

          <FieldRow>
            <Field label="اسم المادة" error={errors.name?.message} required>
              {(props) => <input {...props} {...register('name')} placeholder="خرسانة جاهزة C40" />}
            </Field>
            <Field label="وحدة القياس" error={errors.unit?.message} required>
              {(props) => (
                <input {...props} {...register('unit')} placeholder="م³ / طن / متر طولي" />
              )}
            </Field>
          </FieldRow>

          <FieldRow cols={3}>
            <Field label="الكمية المطلوبة" error={errors.requiredQty?.message} required>
              {(props) => <input {...props} {...register('requiredQty')} type="number" min={0} />}
            </Field>
            <Field label="الكمية المستخدمة" error={errors.usedQty?.message} required>
              {(props) => <input {...props} {...register('usedQty')} type="number" min={0} />}
            </Field>
            <Field
              label="الحد الأدنى للمخزون"
              error={errors.minStockThreshold?.message}
              hint="يُنشئ تنبيهاً تلقائياً"
              required
            >
              {(props) => (
                <input {...props} {...register('minStockThreshold')} type="number" min={0} />
              )}
            </Field>
          </FieldRow>
        </form>
      </Modal>
    </>
  )
}
