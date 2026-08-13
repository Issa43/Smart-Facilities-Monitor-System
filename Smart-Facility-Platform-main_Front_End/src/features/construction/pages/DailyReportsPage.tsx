import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { CalendarDays, Camera, Users } from 'lucide-react'
import type { DailyReport } from '@/types'
import { formatDate, formatNumber, formatPercent } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { createDailyReport, listDailyReports, listProjects } from '@/api/construction'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import {
  ErrorState,
  ProgressBar,
  SkeletonLines,
  StateCard,
} from '@/components/ui/Feedback/Feedback'
import { UploadZone } from '@/components/ui/Display/Display'
import styles from './Quality.module.css'

const schema = z.object({
  projectId: z.string().min(1, 'اختر المشروع'),
  title: z.string().trim().min(5, 'أدخل عنوان التقرير'),
  summary: z.string().trim().min(15, 'اكتب ملخصاً لا يقل عن 15 حرفاً'),
  progressPercent: z.coerce.number().min(0).max(100),
  workforceCount: z.coerce.number().min(0, 'عدد العمالة لا يمكن أن يكون سالباً'),
  photoCount: z.coerce.number().min(0),
})

type ReportFormValues = z.input<typeof schema>

export function DailyReportsPage() {
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [addOpen, setAddOpen] = useState(false)

  const projectsQuery = useQuery({
    queryKey: qk.projects.list(user.id),
    queryFn: () => listProjects(user.id),
  })
  const reportsQuery = useQuery({
    queryKey: qk.dailyReports.all(),
    queryFn: () => listDailyReports(),
  })

  const myProjectIds = new Set(projectsQuery.data?.map((p) => p.id))
  const myReports = reportsQuery.data?.filter((r) => myProjectIds.has(r.projectId)) ?? []
  const projectName = useCallback(
    (id: string) => projectsQuery.data?.find((p) => p.id === id)?.name ?? '—',
    [projectsQuery.data],
  )

  const { query, setQuery, filtered } = useListFilter<DailyReport, 'all'>(myReports, {
    searchText: useCallback((r: DailyReport) => `${r.title} ${r.summary}`, []),
    allValue: 'all',
  })

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ReportFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      projectId: '',
      title: '',
      summary: '',
      progressPercent: 0,
      workforceCount: 0,
      photoCount: 0,
    },
  })

  const create = useMutation({
    mutationFn: (values: ReportFormValues) =>
      createDailyReport({
        projectId: values.projectId,
        title: values.title,
        summary: values.summary,
        progressPercent: Number(values.progressPercent),
        workforceCount: Number(values.workforceCount),
        photoCount: Number(values.photoCount),
        authorId: user.id,
      }),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: qk.dailyReports.all() })
      showToast({ tone: 'success', title: 'تم رفع التقرير اليومي', description: report.title })
      setAddOpen(false)
      reset()
    },
  })

  const sorted = filtered.slice().sort((a, b) => b.reportDate.localeCompare(a.reportDate))

  if (reportsQuery.isError) return <ErrorState error={reportsQuery.error} />

  return (
    <>
      <PageHeader
        title="التقارير اليومية"
        description="توثيق يومي للأعمال المنجزة، عدد العمالة، ونسبة الإنجاز. تُشكّل هذه التقارير السجل الرسمي لسير التنفيذ."
        actions={<Button onClick={() => setAddOpen(true)}>+ تقرير يومي</Button>}
      />

      <Toolbar>
        <SearchInput value={query} onChange={setQuery} placeholder="ابحث في التقارير…" />
      </Toolbar>

      {reportsQuery.isPending ? (
        <SkeletonLines count={6} />
      ) : sorted.length === 0 ? (
        <StateCard
          title="لا توجد تقارير"
          description="ارفع أول تقرير يومي لتوثيق الأعمال المنجزة في الموقع."
        />
      ) : (
        <div className={styles.grid}>
          {sorted.map((report) => (
            <article key={report.id} className={styles.card}>
              <div className={styles.cardHead}>
                <div>
                  <h3 className={styles.cardTitle}>{report.title}</h3>
                  <p className={styles.cardMeta}>{projectName(report.projectId)}</p>
                </div>
                <Badge tone="info" plain>
                  {formatPercent(report.progressPercent)}
                </Badge>
              </div>

              <ProgressBar value={report.progressPercent} size="sm" label="نسبة الإنجاز" />

              <p className={styles.cardNotes}>{report.summary}</p>

              <div className={styles.cardFoot}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <CalendarDays size={12} />
                  {formatDate(report.reportDate)}
                </span>
                <span style={{ display: 'flex', gap: 12 }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <Users size={12} />
                    {formatNumber(report.workforceCount)}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <Camera size={12} />
                    {formatNumber(report.photoCount)}
                  </span>
                </span>
              </div>
            </article>
          ))}
        </div>
      )}

      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="رفع تقرير يومي"
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setAddOpen(false)}>
              إلغاء
            </Button>
            <Button loading={create.isPending} onClick={handleSubmit((v) => create.mutate(v))}>
              رفع التقرير
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

          <Field label="عنوان التقرير" error={errors.title?.message} required>
            {(props) => (
              <input
                {...props}
                {...register('title')}
                placeholder="تقرير يومي — الأعمال الكهروميكانيكية"
              />
            )}
          </Field>

          <Field label="ملخص الأعمال المنجزة" error={errors.summary?.message} required>
            {(props) => <textarea {...props} {...register('summary')} rows={4} />}
          </Field>

          <FieldRow cols={3}>
            <Field label="نسبة الإنجاز" error={errors.progressPercent?.message} required>
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
            <Field label="عدد العمالة" error={errors.workforceCount?.message} required>
              {(props) => (
                <input {...props} {...register('workforceCount')} type="number" min={0} />
              )}
            </Field>
            <Field label="عدد الصور" error={errors.photoCount?.message} required>
              {(props) => <input {...props} {...register('photoCount')} type="number" min={0} />}
            </Field>
          </FieldRow>

          <Field label="صور الموقع">{() => <UploadZone accept="image/*" />}</Field>
        </form>
      </Modal>
    </>
  )
}
