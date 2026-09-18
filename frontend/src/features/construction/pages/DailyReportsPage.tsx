import { useCallback, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { CalendarDays, Camera, Eye, FileText, Pencil, Trash2, Users } from 'lucide-react'
import type { DailyReport } from '@/types'
import { formatDate, formatNumber, formatPercent } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import {
  createDailyReport,
  deleteDailyReport,
  getDailyReport,
  listDailyReports,
  listProjects,
  updateDailyReport,
} from '@/api/construction'
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
import styles from './DailyReportsPage.module.css'

const schema = z.object({
  projectId: z.string().min(1, 'اختر المشروع'),
  title: z.string().trim().min(5, 'أدخل عنوان التقرير'),
  reportDate: z.string().min(1, 'اختر تاريخ التقرير'),
  summary: z.string().trim().min(15, 'اكتب ملخصاً لا يقل عن 15 حرفاً'),
  progressPercent: z.coerce.number().min(0).max(100),
  workforceCount: z.coerce.number().min(0, 'عدد العمالة لا يمكن أن يكون سالباً'),
})

type ReportFormValues = z.input<typeof schema>
type ReportDialog = { id: string; mode: 'view' | 'edit' }

export function DailyReportsPage() {
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [addOpen, setAddOpen] = useState(false)
  const [reportDialog, setReportDialog] = useState<ReportDialog | null>(null)
  const [pendingDelete, setPendingDelete] = useState<DailyReport | null>(null)

  function mutationError(title: string, error: unknown) {
    showToast({
      tone: 'critical',
      title,
      description: error instanceof Error ? error.message : undefined,
    })
  }

  const projectsQuery = useQuery({
    queryKey: qk.projects.list(user.id),
    queryFn: () => listProjects(user.id),
  })
  const reportsQuery = useQuery({
    queryKey: qk.dailyReports.all(),
    queryFn: () => listDailyReports(),
  })
  const detailQuery = useQuery({
    queryKey: qk.dailyReports.detail(reportDialog?.id ?? ''),
    queryFn: () => getDailyReport(reportDialog!.id),
    enabled: reportDialog !== null,
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
      reportDate: new Date().toISOString().slice(0, 10),
      summary: '',
      progressPercent: 0,
      workforceCount: 0,
    },
  })
  const editForm = useForm<ReportFormValues>({ resolver: zodResolver(schema) })

  useEffect(() => {
    if (reportDialog?.mode !== 'edit' || !detailQuery.data) return
    editForm.reset({
      projectId: detailQuery.data.projectId,
      title: detailQuery.data.title,
      reportDate: detailQuery.data.reportDate,
      summary: detailQuery.data.summary,
      progressPercent: detailQuery.data.progressPercent,
      workforceCount: detailQuery.data.workforceCount,
    })
  }, [detailQuery.data, editForm, reportDialog?.mode])

  const create = useMutation({
    mutationFn: (values: ReportFormValues) =>
      createDailyReport({
        projectId: values.projectId,
        title: values.title,
        reportDate: values.reportDate,
        summary: values.summary,
        progressPercent: Number(values.progressPercent),
        workforceCount: Number(values.workforceCount),
      }),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: qk.dailyReports.all() })
      showToast({ tone: 'success', title: 'تم رفع التقرير اليومي', description: report.title })
      setAddOpen(false)
      reset()
    },
    onError: (error) => mutationError('تعذّر رفع التقرير اليومي', error),
  })

  const update = useMutation({
    mutationFn: (values: ReportFormValues) =>
      updateDailyReport(reportDialog!.id, {
        title: values.title,
        reportDate: values.reportDate,
        summary: values.summary,
        progressPercent: Number(values.progressPercent),
        workforceCount: Number(values.workforceCount),
      }),
    onSuccess: (report) => {
      queryClient.setQueryData(qk.dailyReports.detail(report.id), report)
      queryClient.invalidateQueries({ queryKey: qk.dailyReports.all() })
      setReportDialog(null)
      showToast({
        tone: 'success',
        title: 'تم تحديث التقرير اليومي',
        description: report.title,
      })
    },
    onError: (error) => mutationError('تعذّر تحديث التقرير اليومي', error),
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteDailyReport(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.dailyReports.all() })
      setPendingDelete(null)
      showToast({ tone: 'success', title: 'تم حذف التقرير اليومي' })
    },
    onError: (error) => mutationError('تعذّر حذف التقرير اليومي', error),
  })

  const sorted = filtered.slice().sort((a, b) => b.reportDate.localeCompare(a.reportDate))

  const dataError = [projectsQuery, reportsQuery].find((query) => query.isError)?.error
  if (dataError) return <ErrorState error={dataError} />

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

      {projectsQuery.isPending || reportsQuery.isPending ? (
        <SkeletonLines count={6} />
      ) : sorted.length === 0 ? (
        <StateCard
          title="لا توجد تقارير"
          description="ارفع أول تقرير يومي لتوثيق الأعمال المنجزة في الموقع."
        />
      ) : (
        <div className={styles.reportGrid}>
          {sorted.map((report) => (
            <article key={report.id} className={styles.reportCard}>
              <div className={styles.cardBody}>
                <header className={styles.cardHeader}>
                  <div className={styles.reportIcon} aria-hidden="true">
                    <FileText strokeWidth={1.9} />
                  </div>
                  <div className={styles.cardIdentity}>
                    <h3 className={styles.cardTitle}>{report.title}</h3>
                    <p className={styles.cardMeta}>{projectName(report.projectId)}</p>
                  </div>
                  <div className={styles.progressBadge}>
                    <Badge tone="info" plain>
                      {formatPercent(report.progressPercent)}
                    </Badge>
                  </div>
                </header>

                <div className={styles.progressBlock}>
                  <ProgressBar value={report.progressPercent} size="sm" label="نسبة الإنجاز" />
                </div>

                <p className={styles.cardSummary}>{report.summary}</p>

                <div className={styles.metadata}>
                  <div className={styles.metaItem}>
                    <span className={styles.metaIcon} aria-hidden="true">
                      <CalendarDays />
                    </span>
                    <span className={styles.metaText}>
                      <small>التاريخ</small>
                      <strong>{formatDate(report.reportDate)}</strong>
                    </span>
                  </div>
                  <div className={styles.metaItem}>
                    <span className={styles.metaIcon} aria-hidden="true">
                      <Users />
                    </span>
                    <span className={styles.metaText}>
                      <small>العمالة</small>
                      <strong>{formatNumber(report.workforceCount)}</strong>
                    </span>
                  </div>
                  <div className={styles.metaItem}>
                    <span className={styles.metaIcon} aria-hidden="true">
                      <Camera />
                    </span>
                    <span className={styles.metaText}>
                      <small>الصور</small>
                      <strong>{formatNumber(report.photoCount)}</strong>
                    </span>
                  </div>
                </div>
              </div>

              <footer className={styles.cardActions} aria-label="إجراءات التقرير">
                <Button
                  size="sm"
                  variant="primary"
                  className={styles.actionButton}
                  onClick={() => setReportDialog({ id: report.id, mode: 'view' })}
                >
                  <Eye /> <span>استعراض</span>
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className={styles.actionButton}
                  onClick={() => setReportDialog({ id: report.id, mode: 'edit' })}
                >
                  <Pencil /> <span>تعديل</span>
                </Button>
                <Button
                  size="sm"
                  variant="critical"
                  className={styles.actionButton}
                  onClick={() => setPendingDelete(report)}
                >
                  <Trash2 /> <span>حذف</span>
                </Button>
              </footer>
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

          <Field label="تاريخ التقرير" error={errors.reportDate?.message} required>
            {(props) => <input {...props} {...register('reportDate')} type="date" />}
          </Field>

          <Field label="ملخص الأعمال المنجزة" error={errors.summary?.message} required>
            {(props) => <textarea {...props} {...register('summary')} rows={4} />}
          </Field>

          <FieldRow>
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
          </FieldRow>
        </form>
      </Modal>

      <Modal
        open={reportDialog !== null}
        onClose={() => setReportDialog(null)}
        title={reportDialog?.mode === 'edit' ? 'تعديل التقرير اليومي' : 'تفاصيل التقرير اليومي'}
        subtitle={detailQuery.data?.title}
        size="lg"
        footer={
          reportDialog?.mode === 'edit' && detailQuery.data ? (
            <>
              <Button variant="ghost" onClick={() => setReportDialog(null)}>
                إلغاء
              </Button>
              <Button
                loading={update.isPending}
                onClick={editForm.handleSubmit((values) => update.mutate(values))}
              >
                حفظ التعديلات
              </Button>
            </>
          ) : (
            <Button variant="ghost" onClick={() => setReportDialog(null)}>
              إغلاق
            </Button>
          )
        }
      >
        {detailQuery.isPending ? (
          <SkeletonLines count={5} />
        ) : detailQuery.isError ? (
          <ErrorState bare error={detailQuery.error} onRetry={() => void detailQuery.refetch()} />
        ) : detailQuery.data && reportDialog?.mode === 'edit' ? (
          <form onSubmit={editForm.handleSubmit((values) => update.mutate(values))} noValidate>
            <Field label="المشروع">
              {(props) => (
                <input {...props} value={projectName(detailQuery.data.projectId)} disabled />
              )}
            </Field>
            <Field label="عنوان التقرير" error={editForm.formState.errors.title?.message} required>
              {(props) => <input {...props} {...editForm.register('title')} />}
            </Field>
            <Field
              label="تاريخ التقرير"
              error={editForm.formState.errors.reportDate?.message}
              required
            >
              {(props) => <input {...props} {...editForm.register('reportDate')} type="date" />}
            </Field>
            <Field
              label="ملخص الأعمال المنجزة"
              error={editForm.formState.errors.summary?.message}
              required
            >
              {(props) => <textarea {...props} {...editForm.register('summary')} rows={4} />}
            </Field>
            <FieldRow>
              <Field
                label="نسبة الإنجاز"
                error={editForm.formState.errors.progressPercent?.message}
                required
              >
                {(props) => (
                  <input
                    {...props}
                    {...editForm.register('progressPercent')}
                    type="number"
                    min={0}
                    max={100}
                  />
                )}
              </Field>
              <Field
                label="عدد العمالة"
                error={editForm.formState.errors.workforceCount?.message}
                required
              >
                {(props) => (
                  <input
                    {...props}
                    {...editForm.register('workforceCount')}
                    type="number"
                    min={0}
                  />
                )}
              </Field>
            </FieldRow>
          </form>
        ) : detailQuery.data ? (
          <dl
            style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(120px, auto) 1fr',
              gap: '12px 20px',
              margin: 0,
            }}
          >
            <dt style={{ color: 'var(--text-muted)' }}>المشروع</dt>
            <dd style={{ margin: 0 }}>{projectName(detailQuery.data.projectId)}</dd>
            <dt style={{ color: 'var(--text-muted)' }}>التاريخ</dt>
            <dd style={{ margin: 0 }}>{formatDate(detailQuery.data.reportDate)}</dd>
            <dt style={{ color: 'var(--text-muted)' }}>ملخص الأعمال</dt>
            <dd style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{detailQuery.data.summary}</dd>
            <dt style={{ color: 'var(--text-muted)' }}>نسبة الإنجاز</dt>
            <dd style={{ margin: 0 }}>{formatPercent(detailQuery.data.progressPercent)}</dd>
            <dt style={{ color: 'var(--text-muted)' }}>عدد العمالة</dt>
            <dd style={{ margin: 0 }}>{formatNumber(detailQuery.data.workforceCount)}</dd>
            <dt style={{ color: 'var(--text-muted)' }}>الصور المرتبطة</dt>
            <dd style={{ margin: 0 }}>{formatNumber(detailQuery.data.photoCount)}</dd>
            <dt style={{ color: 'var(--text-muted)' }}>أعدّه</dt>
            <dd style={{ margin: 0 }}>{detailQuery.data.authorName ?? '—'}</dd>
          </dl>
        ) : null}
      </Modal>

      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title="تأكيد حذف التقرير اليومي"
        subtitle={pendingDelete?.title}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setPendingDelete(null)}>
              إلغاء
            </Button>
            <Button
              variant="critical"
              loading={remove.isPending}
              onClick={() => pendingDelete && remove.mutate(pendingDelete.id)}
            >
              حذف التقرير
            </Button>
          </>
        }
      >
        سيتم حذف التقرير من سجل المشروع.
      </Modal>
    </>
  )
}
