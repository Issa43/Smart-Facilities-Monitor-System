import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import type { InspectionResult, QualityInspection } from '@/types'
import { INSPECTION_RESULT_LABELS, INSPECTION_RESULT_TONE } from '@/types'
import { formatDate, formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { createInspection, listInspections, listProjects, listStages } from '@/api/construction'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { Panel } from '@/components/ui/Panel/Panel'
import { ErrorState, ProgressBar, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section, UploadZone } from '@/components/ui/Display/Display'
import styles from './Quality.module.css'

type ResultFilter = InspectionResult | 'all'

const FILTERS: { value: ResultFilter; label: string }[] = [
  { value: 'all', label: 'الكل' },
  { value: 'passed', label: 'مطابق' },
  { value: 'passed_with_notes', label: 'مطابق مع ملاحظات' },
  { value: 'failed', label: 'غير مطابق' },
]

const schema = z.object({
  projectId: z.string().min(1, 'اختر المشروع'),
  stageId: z.string().min(1, 'اختر المرحلة'),
  title: z.string().trim().min(5, 'أدخل عنواناً للفحص'),
  score: z.coerce.number().min(0, 'الدرجة بين 0 و 100').max(100, 'الدرجة بين 0 و 100'),
  result: z.string().min(1, 'اختر نتيجة الفحص'),
  notes: z.string().trim().min(5, 'أدخل ملاحظات الفحص'),
})

type InspectionFormValues = z.input<typeof schema>

export function QualityInspectionsPage() {
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [addOpen, setAddOpen] = useState(false)

  const projectsQuery = useQuery({
    queryKey: qk.projects.list(user.id),
    queryFn: () => listProjects(user.id),
  })
  const stagesQuery = useQuery({ queryKey: qk.stages.all, queryFn: () => listStages() })
  const inspectionsQuery = useQuery({
    queryKey: qk.quality.inspections(),
    queryFn: () => listInspections(),
  })

  const myProjectIds = new Set(projectsQuery.data?.map((p) => p.id))
  const myInspections =
    inspectionsQuery.data?.filter((inspection) => myProjectIds.has(inspection.projectId)) ?? []

  const projectName = useCallback(
    (id: string) => projectsQuery.data?.find((p) => p.id === id)?.name ?? '—',
    [projectsQuery.data],
  )
  const stageName = useCallback(
    (id: string) => stagesQuery.data?.find((s) => s.id === id)?.name ?? '—',
    [stagesQuery.data],
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<
    QualityInspection,
    ResultFilter
  >(myInspections, {
    searchText: useCallback((i: QualityInspection) => `${i.title} ${i.notes}`, []),
    matchesFilter: useCallback((i: QualityInspection, v: ResultFilter) => i.result === v, []),
    allValue: 'all',
  })

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<InspectionFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      projectId: '',
      stageId: '',
      title: '',
      score: 90,
      result: 'passed',
      notes: '',
    },
  })

  const selectedProject = watch('projectId')

  const create = useMutation({
    mutationFn: (values: InspectionFormValues) =>
      createInspection({
        projectId: values.projectId,
        stageId: values.stageId,
        title: values.title,
        inspectorId: user.id,
        score: Number(values.score),
        result: values.result as InspectionResult,
        notes: values.notes,
      }),
    onSuccess: (inspection) => {
      queryClient.invalidateQueries({ queryKey: qk.quality.inspections() })
      queryClient.invalidateQueries({ queryKey: qk.stats.construction(user.id) })
      showToast({ tone: 'success', title: 'تم تسجيل الفحص', description: inspection.title })
      setAddOpen(false)
      reset()
    },
  })

  const counts = FILTERS.map((option) => ({
    ...option,
    count:
      option.value === 'all'
        ? myInspections.length
        : myInspections.filter((i) => i.result === option.value).length,
  }))

  const average =
    myInspections.length === 0
      ? 0
      : Math.round(myInspections.reduce((sum, i) => sum + i.score, 0) / myInspections.length)
  const failed = myInspections.filter((i) => i.result === 'failed')

  if (inspectionsQuery.isError) return <ErrorState error={inspectionsQuery.error} />

  return (
    <>
      <PageHeader
        title="فحوصات الجودة"
        description="توثيق نتائج فحص الأعمال المنجزة لكل مرحلة. الفحوصات غير المطابقة تستوجب إعادة التنفيذ قبل اعتماد المرحلة."
        actions={<Button onClick={() => setAddOpen(true)}>+ فحص جديد</Button>}
      />

      <Section>
        <KpiGrid cols={3}>
          <KpiCard
            label="إجمالي الفحوصات"
            value={formatNumber(myInspections.length)}
            icon="quality"
            tone="primary"
            loading={inspectionsQuery.isPending}
          />
          <KpiCard
            label="متوسط الدرجة"
            value={average === 0 ? '—' : formatNumber(average)}
            icon="progress"
            tone={average >= 85 ? 'success' : 'warning'}
            loading={inspectionsQuery.isPending}
            progress={average}
          />
          <KpiCard
            label="فحوصات غير مطابقة"
            value={formatNumber(failed.length)}
            icon="faults"
            tone={failed.length > 0 ? 'critical' : 'success'}
            loading={inspectionsQuery.isPending}
            footnote={failed.length > 0 ? 'تتطلب إعادة تنفيذ' : 'جميع الفحوصات مطابقة'}
            footnoteTone={failed.length > 0 ? 'critical' : 'success'}
          />
        </KpiGrid>
      </Section>

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput value={query} onChange={setQuery} placeholder="ابحث بعنوان الفحص…" />
          <FilterBar
            options={counts}
            value={filter}
            onChange={setFilter}
            label="تصفية الفحوصات حسب النتيجة"
          />
        </div>
      </Toolbar>

      {inspectionsQuery.isPending ? (
        <Panel>
          <ProgressBar value={0} />
        </Panel>
      ) : filtered.length === 0 ? (
        <StateCard
          title="لا توجد فحوصات مطابقة"
          description="سجّل فحص جودة جديد أو غيّر عوامل التصفية."
        />
      ) : (
        <div className={styles.grid}>
          {filtered.map((inspection) => (
            <article key={inspection.id} className={styles.card}>
              <div className={styles.cardHead}>
                <div>
                  <h3 className={styles.cardTitle}>{inspection.title}</h3>
                  <p className={styles.cardMeta}>
                    {projectName(inspection.projectId)} · {stageName(inspection.stageId)}
                  </p>
                </div>
                <Badge tone={INSPECTION_RESULT_TONE[inspection.result]}>
                  {INSPECTION_RESULT_LABELS[inspection.result]}
                </Badge>
              </div>

              <div className={styles.scoreRow}>
                <span className={styles.scoreLabel}>الدرجة</span>
                <span
                  className={styles.scoreValue}
                  style={{
                    color:
                      inspection.score >= 85
                        ? 'var(--success-dark)'
                        : inspection.score >= 70
                          ? 'var(--warning-dark)'
                          : 'var(--critical-dark)',
                  }}
                >
                  {formatNumber(inspection.score)}
                </span>
              </div>
              <ProgressBar value={inspection.score} size="sm" label="درجة الفحص" />

              <p className={styles.cardNotes}>{inspection.notes}</p>

              <div className={styles.cardFoot}>
                <span>{formatDate(inspection.inspectedAt)}</span>
              </div>
            </article>
          ))}
        </div>
      )}

      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="تسجيل فحص جودة"
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setAddOpen(false)}>
              إلغاء
            </Button>
            <Button loading={create.isPending} onClick={handleSubmit((v) => create.mutate(v))}>
              حفظ الفحص
            </Button>
          </>
        }
      >
        <form onSubmit={handleSubmit((v) => create.mutate(v))} noValidate>
          <FieldRow>
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

            <Field label="المرحلة" error={errors.stageId?.message} required>
              {(props) => (
                <select {...props} {...register('stageId')} disabled={!selectedProject}>
                  <option value="">
                    {selectedProject ? 'اختر المرحلة…' : 'اختر المشروع أولاً'}
                  </option>
                  {stagesQuery.data
                    ?.filter((stage) => stage.projectId === selectedProject)
                    .map((stage) => (
                      <option key={stage.id} value={stage.id}>
                        {stage.name}
                      </option>
                    ))}
                </select>
              )}
            </Field>
          </FieldRow>

          <Field label="عنوان الفحص" error={errors.title?.message} required>
            {(props) => (
              <input
                {...props}
                {...register('title')}
                placeholder="فحص عينات الخرسانة — الطابق الثاني"
              />
            )}
          </Field>

          <FieldRow>
            <Field label="الدرجة" error={errors.score?.message} hint="0 – 100" required>
              {(props) => (
                <input {...props} {...register('score')} type="number" min={0} max={100} />
              )}
            </Field>
            <Field label="النتيجة" error={errors.result?.message} required>
              {(props) => (
                <select {...props} {...register('result')}>
                  {Object.entries(INSPECTION_RESULT_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </FieldRow>

          <Field label="ملاحظات الفحص" error={errors.notes?.message} required>
            {(props) => <textarea {...props} {...register('notes')} rows={3} />}
          </Field>

          <Field label="المرفقات">
            {() => <UploadZone hint="صور أو تقارير مخبرية — PDF أو صور" />}
          </Field>
        </form>
      </Modal>
    </>
  )
}
