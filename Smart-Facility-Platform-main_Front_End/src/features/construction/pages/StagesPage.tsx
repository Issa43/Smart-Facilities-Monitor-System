import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import type { Priority, Stage, StageStatus } from '@/types'
import { PRIORITY_LABELS, PRIORITY_TONE, STAGE_STATUS_LABELS, STAGE_STATUS_TONE } from '@/types'
import { formatDate, formatNumber, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { createStage, listProjects, listStages } from '@/api/construction'
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
import { ErrorState, ProgressBar, StateCard } from '@/components/ui/Feedback/Feedback'

type StageFilter = StageStatus | 'all'

const FILTERS: { value: StageFilter; label: string }[] = [
  { value: 'all', label: 'الكل' },
  { value: 'not_started', label: 'لم تبدأ' },
  { value: 'in_progress', label: 'قيد التنفيذ' },
  { value: 'under_review', label: 'قيد المراجعة' },
  { value: 'completed', label: 'مكتملة' },
  { value: 'rejected', label: 'مرفوضة' },
]

const schema = z
  .object({
    projectId: z.string().min(1, 'اختر المشروع'),
    name: z.string().trim().min(3, 'اسم المرحلة يجب ألا يقل عن 3 أحرف'),
    description: z.string().trim().min(10, 'أدخل وصفاً لا يقل عن 10 أحرف'),
    startDate: z.string().min(1, 'اختر تاريخ البداية'),
    expectedEndDate: z.string().min(1, 'اختر تاريخ النهاية المتوقع'),
    progressPercent: z.coerce.number().min(0, 'النسبة بين 0 و 100').max(100, 'النسبة بين 0 و 100'),
    priority: z.string().min(1, 'اختر الأولوية'),
    status: z.string().min(1, 'اختر الحالة'),
  })
  .refine((values) => new Date(values.expectedEndDate) > new Date(values.startDate), {
    message: 'تاريخ النهاية يجب أن يكون بعد تاريخ البداية',
    path: ['expectedEndDate'],
  })

type StageFormValues = z.input<typeof schema>

export function StagesPage() {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [addOpen, setAddOpen] = useState(false)

  const projectsQuery = useQuery({
    queryKey: qk.projects.list(user.id),
    queryFn: () => listProjects(user.id),
  })
  const stagesQuery = useQuery({ queryKey: qk.stages.all, queryFn: () => listStages() })

  const myProjectIds = new Set(projectsQuery.data?.map((p) => p.id))
  const myStages = stagesQuery.data?.filter((stage) => myProjectIds.has(stage.projectId)) ?? []
  const projectName = useCallback(
    (id: string) => projectsQuery.data?.find((p) => p.id === id)?.name ?? '—',
    [projectsQuery.data],
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<Stage, StageFilter>(
    myStages,
    {
      searchText: useCallback((stage: Stage) => `${stage.name} ${stage.description}`, []),
      matchesFilter: useCallback((stage: Stage, value: StageFilter) => stage.status === value, []),
      allValue: 'all',
    },
  )

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<StageFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      projectId: '',
      name: '',
      description: '',
      startDate: '',
      expectedEndDate: '',
      progressPercent: 0,
      priority: 'medium',
      status: 'not_started',
    },
  })

  const create = useMutation({
    mutationFn: (values: StageFormValues) =>
      createStage({
        projectId: values.projectId,
        name: values.name,
        description: values.description,
        startDate: new Date(values.startDate).toISOString(),
        expectedEndDate: new Date(values.expectedEndDate).toISOString(),
        progressPercent: Number(values.progressPercent),
        priority: values.priority as Priority,
        status: values.status as StageStatus,
      }),
    onSuccess: (stage) => {
      queryClient.invalidateQueries({ queryKey: qk.stages.all })
      queryClient.invalidateQueries({ queryKey: qk.projects.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.construction(user.id) })
      showToast({ tone: 'success', title: 'تمت إضافة المرحلة', description: stage.name })
      setAddOpen(false)
      reset()
    },
  })

  const counts = FILTERS.map((option) => ({
    ...option,
    count:
      option.value === 'all'
        ? myStages.length
        : myStages.filter((stage) => stage.status === option.value).length,
  }))

  if (stagesQuery.isError) return <ErrorState error={stagesQuery.error} />

  return (
    <>
      <PageHeader
        title="مراحل التنفيذ"
        description={`${formatNumber(myStages.length)} مرحلة عبر مشاريعك. كل مرحلة تمر بدورة: لم تبدأ ← قيد التنفيذ ← قيد المراجعة ← معتمدة.`}
        actions={<Button onClick={() => setAddOpen(true)}>+ مرحلة جديدة</Button>}
      />

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput value={query} onChange={setQuery} placeholder="ابحث باسم المرحلة…" />
          <FilterBar
            options={counts}
            value={filter}
            onChange={setFilter}
            label="تصفية المراحل حسب الحالة"
          />
        </div>
      </Toolbar>

      <DataTable
        loading={stagesQuery.isPending}
        rows={filtered}
        rowKey={(stage) => stage.id}
        onRowClick={(stage) => navigate(`/construction/stages/${stage.id}`)}
        columns={[
          {
            key: 'name',
            header: 'المرحلة',
            sortValue: (stage) => stage.name,
            render: (stage) => (
              <div>
                <div style={{ fontWeight: 700 }}>{stage.name}</div>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>
                  {projectName(stage.projectId)}
                </div>
              </div>
            ),
          },
          {
            key: 'priority',
            header: 'الأولوية',
            sortValue: (stage) => stage.priority,
            render: (stage) => (
              <Badge tone={PRIORITY_TONE[stage.priority]}>{PRIORITY_LABELS[stage.priority]}</Badge>
            ),
          },
          {
            key: 'progress',
            header: 'نسبة الإنجاز',
            width: '190px',
            sortValue: (stage) => stage.progressPercent,
            render: (stage) => <ProgressBar value={stage.progressPercent} size="sm" showValue />,
          },
          {
            key: 'end',
            header: 'النهاية المتوقعة',
            sortValue: (stage) => stage.expectedEndDate,
            render: (stage) => {
              const overdue =
                stage.status !== 'completed' &&
                new Date(stage.expectedEndDate).getTime() < Date.now()
              return (
                <span
                  style={{
                    color: overdue ? 'var(--critical-dark)' : undefined,
                    fontWeight: overdue ? 700 : undefined,
                  }}
                >
                  {formatDate(stage.expectedEndDate)}
                  {overdue && ' (متأخرة)'}
                </span>
              )
            },
          },
          {
            key: 'updated',
            header: 'آخر تحديث',
            sortValue: (stage) => stage.updatedAt,
            render: (stage) => formatRelative(stage.updatedAt),
          },
          {
            key: 'status',
            header: 'الحالة',
            sortValue: (stage) => stage.status,
            render: (stage) => (
              <Badge tone={STAGE_STATUS_TONE[stage.status]}>
                {STAGE_STATUS_LABELS[stage.status]}
              </Badge>
            ),
          },
        ]}
        empty={
          <StateCard
            bare
            title="لا توجد مراحل مطابقة"
            description="أضف مرحلة جديدة أو غيّر عوامل التصفية."
          />
        }
      />

      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="إضافة مرحلة تنفيذ"
        subtitle="بعد الحفظ تصبح المرحلة جاهزة للمتابعة وتُحتسب ضمن نسبة إنجاز المشروع."
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
              حفظ المرحلة
            </Button>
          </>
        }
      >
        <form onSubmit={handleSubmit((values) => create.mutate(values))} noValidate>
          <Field label="المشروع" error={errors.projectId?.message} required>
            {(props) => (
              <select {...props} {...register('projectId')}>
                <option value="">اختر المشروع…</option>
                {projectsQuery.data
                  ?.filter((project) => project.status !== 'operational')
                  .map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
              </select>
            )}
          </Field>

          <Field label="اسم المرحلة" error={errors.name?.message} required>
            {(props) => (
              <input {...props} {...register('name')} placeholder="مثال: الهيكل الخرساني" />
            )}
          </Field>

          <Field label="وصف المرحلة" error={errors.description?.message} required>
            {(props) => <textarea {...props} {...register('description')} rows={3} />}
          </Field>

          <FieldRow>
            <Field label="تاريخ البداية" error={errors.startDate?.message} required>
              {(props) => <input {...props} {...register('startDate')} type="date" />}
            </Field>
            <Field label="النهاية المتوقعة" error={errors.expectedEndDate?.message} required>
              {(props) => <input {...props} {...register('expectedEndDate')} type="date" />}
            </Field>
          </FieldRow>

          <FieldRow cols={3}>
            <Field
              label="نسبة الإنجاز الابتدائية"
              error={errors.progressPercent?.message}
              hint="0 – 100"
              required
            >
              {(props) => (
                <input
                  {...props}
                  {...register('progressPercent')}
                  type="number"
                  min={0}
                  max={100}
                />
              )}
            </Field>
            <Field label="الأولوية" error={errors.priority?.message} required>
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
            <Field label="الحالة" error={errors.status?.message} required>
              {(props) => (
                <select {...props} {...register('status')}>
                  {Object.entries(STAGE_STATUS_LABELS)
                    .filter(([value]) => value !== 'rejected')
                    .map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
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
