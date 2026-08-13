import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { Check, RotateCcw, X } from 'lucide-react'
import {
  INSPECTION_RESULT_LABELS,
  INSPECTION_RESULT_TONE,
  PRIORITY_LABELS,
  PRIORITY_TONE,
  STAGE_STATUS_LABELS,
  STAGE_STATUS_TONE,
} from '@/types'
import { formatDate, formatNumber, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import {
  addStageUpdate,
  getProject,
  getStage,
  listInspections,
  listStageUpdates,
  reviewStage,
  type StageReviewDecision,
} from '@/api/construction'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { Field } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { Panel } from '@/components/ui/Panel/Panel'
import {
  Alert,
  ErrorState,
  ProgressBar,
  SkeletonLines,
  StateCard,
} from '@/components/ui/Feedback/Feedback'
import { DescriptionList, Section, SplitGrid, Timeline } from '@/components/ui/Display/Display'
import { ProgressRing } from '@/components/charts/Charts'
import shared from '@/features/shared/Dashboard.module.css'
import styles from '@/features/shared/ProjectDetail.module.css'

const DECISION_COPY: Record<StageReviewDecision, { title: string; body: string; confirm: string }> =
  {
    approve: {
      title: 'اعتماد المرحلة',
      body: 'سيتم تعيين نسبة الإنجاز إلى 100% وتغيير حالة المرحلة إلى «مكتملة». تُحتسب المرحلة ضمن شروط إنهاء المشروع.',
      confirm: 'اعتماد المرحلة',
    },
    reject: {
      title: 'رفض المرحلة',
      body: 'ستتحول حالة المرحلة إلى «مرفوضة». المشروع لا يمكن إنهاؤه ما دامت هناك مرحلة مرفوضة.',
      confirm: 'رفض المرحلة',
    },
    return: {
      title: 'إعادة المرحلة للتعديل',
      body: 'ستعود المرحلة إلى حالة «قيد التنفيذ» ليتمكن الفريق من معالجة الملاحظات.',
      confirm: 'إعادة للتعديل',
    },
  }

export function StageDetailPage() {
  const { stageId = '' } = useParams<{ stageId: string }>()
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const { showToast } = useToast()

  const [decision, setDecision] = useState<StageReviewDecision | null>(null)
  const [reviewNote, setReviewNote] = useState('')
  const [updateOpen, setUpdateOpen] = useState(false)
  const [progressDraft, setProgressDraft] = useState(0)
  const [completedWork, setCompletedWork] = useState('')
  const [note, setNote] = useState('')

  const stageQuery = useQuery({
    queryKey: qk.stages.detail(stageId),
    queryFn: () => getStage(stageId),
  })
  const stage = stageQuery.data

  const projectQuery = useQuery({
    queryKey: qk.projects.detail(stage?.projectId ?? ''),
    queryFn: () => getProject(stage?.projectId as string),
    enabled: Boolean(stage?.projectId),
  })
  const updatesQuery = useQuery({
    queryKey: qk.stages.updates(stageId),
    queryFn: () => listStageUpdates(stageId),
  })
  const inspectionsQuery = useQuery({
    queryKey: qk.quality.inspections(stage?.projectId),
    queryFn: () => listInspections(stage?.projectId),
    enabled: Boolean(stage?.projectId),
  })

  function invalidateStage() {
    queryClient.invalidateQueries({ queryKey: qk.stages.all })
    queryClient.invalidateQueries({ queryKey: qk.projects.all })
    queryClient.invalidateQueries({ queryKey: qk.stats.construction(user.id) })
  }

  const review = useMutation({
    mutationFn: (input: { decision: StageReviewDecision; note: string }) =>
      reviewStage(stageId, input.decision, input.note),
    onSuccess: (updated, variables) => {
      invalidateStage()
      setDecision(null)
      setReviewNote('')
      showToast({
        tone: variables.decision === 'reject' ? 'critical' : 'success',
        title: DECISION_COPY[variables.decision].title + ' — تم',
        description: updated.name,
      })
    },
  })

  const submitUpdate = useMutation({
    mutationFn: () =>
      addStageUpdate({
        stageId,
        progressPercent: progressDraft,
        completedWork,
        note,
        photoCount: 0,
        authorId: user.id,
      }),
    onSuccess: () => {
      invalidateStage()
      queryClient.invalidateQueries({ queryKey: qk.stages.updates(stageId) })
      setUpdateOpen(false)
      setCompletedWork('')
      setNote('')
      showToast({ tone: 'success', title: 'تم تسجيل تحديث التنفيذ' })
    },
  })

  if (stageQuery.isError) return <ErrorState error={stageQuery.error} />
  if (stageQuery.isPending || !stage) {
    return (
      <Panel>
        <SkeletonLines count={7} />
      </Panel>
    )
  }

  const stageInspections = (inspectionsQuery.data ?? []).filter(
    (inspection) => inspection.stageId === stage.id,
  )
  const overdue =
    stage.status !== 'completed' && new Date(stage.expectedEndDate).getTime() < Date.now()

  return (
    <>
      <PageHeader
        title={stage.name}
        description={stage.description}
        crumbs={[{ label: stage.name }]}
        actions={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                setProgressDraft(stage.progressPercent)
                setUpdateOpen(true)
              }}
              disabled={stage.status === 'completed'}
            >
              تحديث التنفيذ
            </Button>
            {stage.status === 'under_review' && (
              <>
                <Button variant="critical" onClick={() => setDecision('reject')}>
                  <X size={15} strokeWidth={2.2} />
                  رفض
                </Button>
                <Button variant="success" onClick={() => setDecision('approve')}>
                  <Check size={15} strokeWidth={2.2} />
                  اعتماد
                </Button>
              </>
            )}
          </>
        }
      />

      {overdue && (
        <Section>
          <Alert
            tone="warning"
            title="المرحلة متأخرة عن الجدول"
            description={`تجاوزت المرحلة تاريخ النهاية المتوقع (${formatDate(stage.expectedEndDate)}) ولم تكتمل بعد.`}
          />
        </Section>
      )}

      {stage.status === 'rejected' && stage.reviewNote && (
        <Section>
          <Alert tone="critical" title="مرحلة مرفوضة" description={stage.reviewNote} />
        </Section>
      )}

      <Section>
        <div className={styles.hero}>
          <ProgressRing percent={stage.progressPercent} size={128} label="نسبة الإنجاز" />
          <div className={styles.heroBody}>
            <div className={styles.heroTop}>
              <Badge tone={STAGE_STATUS_TONE[stage.status]}>
                {STAGE_STATUS_LABELS[stage.status]}
              </Badge>
              <Badge tone={PRIORITY_TONE[stage.priority]}>
                أولوية {PRIORITY_LABELS[stage.priority]}
              </Badge>
            </div>
            <DescriptionList
              items={[
                {
                  label: 'المشروع',
                  value: projectQuery.data ? (
                    <Link
                      to={`/construction/projects/${projectQuery.data.id}`}
                      style={{ color: 'var(--primary-dark)', fontWeight: 700 }}
                    >
                      {projectQuery.data.name}
                    </Link>
                  ) : (
                    '—'
                  ),
                },
                { label: 'تاريخ البداية', value: formatDate(stage.startDate) },
                { label: 'النهاية المتوقعة', value: formatDate(stage.expectedEndDate) },
                { label: 'آخر تحديث', value: formatRelative(stage.updatedAt) },
                { label: 'عدد التحديثات', value: formatNumber(updatesQuery.data?.length ?? 0) },
                { label: 'فحوصات الجودة', value: formatNumber(stageInspections.length) },
              ]}
            />
          </div>
        </div>
      </Section>

      <SplitGrid>
        <Panel title="سجل تحديثات التنفيذ" subtitle="كل تحديث يُحفظ بشكل دائم ولا يمكن تعديله">
          {updatesQuery.isPending ? (
            <SkeletonLines count={5} />
          ) : (updatesQuery.data?.length ?? 0) === 0 ? (
            <StateCard
              bare
              title="لا توجد تحديثات بعد"
              description="سجّل أول تحديث تنفيذ لتوثيق الأعمال المنجزة."
            />
          ) : (
            <Timeline
              entries={(updatesQuery.data ?? []).map((update) => ({
                id: update.id,
                tone: update.progressPercent >= 100 ? 'success' : 'info',
                title: `نسبة الإنجاز: ${update.progressPercent}%`,
                body: (
                  <>
                    {update.completedWork}
                    {update.note && (
                      <span style={{ display: 'block', marginTop: 4, color: 'var(--text-faint)' }}>
                        ملاحظة: {update.note}
                      </span>
                    )}
                  </>
                ),
                meta: `${formatRelative(update.createdAt)} · ${formatNumber(update.photoCount)} صورة مرفقة`,
              }))}
            />
          )}
        </Panel>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Panel title="مراجعة الجودة">
            {stage.status === 'under_review' ? (
              <>
                <p className={shared.hint} style={{ marginBottom: 14 }}>
                  المرحلة بلغت نسبة إنجاز 100% وهي بانتظار قرارك.
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <Button variant="success" block onClick={() => setDecision('approve')}>
                    <Check size={15} strokeWidth={2.2} />
                    اعتماد المرحلة
                  </Button>
                  <Button variant="ghost" block onClick={() => setDecision('return')}>
                    <RotateCcw size={15} strokeWidth={2} />
                    إعادة للتعديل
                  </Button>
                  <Button variant="critical" block onClick={() => setDecision('reject')}>
                    <X size={15} strokeWidth={2.2} />
                    رفض المرحلة
                  </Button>
                </div>
              </>
            ) : stage.status === 'completed' ? (
              <Alert
                tone="success"
                title="المرحلة معتمدة"
                description={stage.reviewNote ?? 'تم اعتماد المرحلة بعد مراجعة الأعمال المنجزة.'}
              />
            ) : (
              <p className={shared.hint}>
                تصبح المرحلة جاهزة للمراجعة تلقائياً عندما تبلغ نسبة الإنجاز 100%.
              </p>
            )}
          </Panel>

          <Panel title="فحوصات الجودة المرتبطة">
            {stageInspections.length === 0 ? (
              <p className={shared.hint}>لا توجد فحوصات جودة مسجّلة لهذه المرحلة.</p>
            ) : (
              <div className={shared.attentionList}>
                {stageInspections.map((inspection) => (
                  <div key={inspection.id} className={shared.attentionRow}>
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span className={shared.attentionTitle}>{inspection.title}</span>
                      <span className={shared.attentionMeta}>
                        الدرجة {formatNumber(inspection.score)} ·{' '}
                        {formatDate(inspection.inspectedAt)}
                      </span>
                    </span>
                    <Badge tone={INSPECTION_RESULT_TONE[inspection.result]}>
                      {INSPECTION_RESULT_LABELS[inspection.result]}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      </SplitGrid>

      {/* ---------- Review decision ---------- */}
      <Modal
        open={decision !== null}
        onClose={() => setDecision(null)}
        title={decision ? DECISION_COPY[decision].title : ''}
        subtitle={stage.name}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDecision(null)}>
              إلغاء
            </Button>
            <Button
              variant={decision === 'reject' ? 'critical' : 'primary'}
              loading={review.isPending}
              onClick={() => decision && review.mutate({ decision, note: reviewNote })}
            >
              {decision ? DECISION_COPY[decision].confirm : ''}
            </Button>
          </>
        }
      >
        <p style={{ fontSize: 13, lineHeight: 1.9, color: 'var(--text-muted)', marginBottom: 16 }}>
          {decision ? DECISION_COPY[decision].body : ''}
        </p>
        <Field label="ملاحظات المراجعة" hint="تُحفظ مع المرحلة وتظهر لفريق التنفيذ">
          {(props) => (
            <textarea
              {...props}
              rows={4}
              value={reviewNote}
              onChange={(event) => setReviewNote(event.target.value)}
              placeholder="اكتب ملاحظاتك على الأعمال المنجزة…"
            />
          )}
        </Field>
      </Modal>

      {/* ---------- Progress update ---------- */}
      <Modal
        open={updateOpen}
        onClose={() => setUpdateOpen(false)}
        title="تحديث تنفيذ المرحلة"
        subtitle="عند بلوغ 100% تنتقل المرحلة تلقائياً إلى «قيد المراجعة»."
        footer={
          <>
            <Button variant="ghost" onClick={() => setUpdateOpen(false)}>
              إلغاء
            </Button>
            <Button
              loading={submitUpdate.isPending}
              disabled={completedWork.trim().length < 5}
              onClick={() => submitUpdate.mutate()}
            >
              حفظ التحديث
            </Button>
          </>
        }
      >
        <Field label={`نسبة الإنجاز — ${progressDraft}%`}>
          {() => (
            <>
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={progressDraft}
                onChange={(event) => setProgressDraft(Number(event.target.value))}
                style={{ width: '100%', accentColor: 'var(--primary-dark)', padding: 0 }}
                aria-label="نسبة الإنجاز"
              />
              <div style={{ marginTop: 10 }}>
                <ProgressBar value={progressDraft} label="نسبة الإنجاز" />
              </div>
            </>
          )}
        </Field>

        <Field label="وصف الأعمال المنجزة" hint="5 أحرف على الأقل" required>
          {(props) => (
            <textarea
              {...props}
              rows={3}
              value={completedWork}
              onChange={(event) => setCompletedWork(event.target.value)}
              placeholder="مثال: اكتمال صب أسقف الطابق الثاني…"
            />
          )}
        </Field>

        <Field label="ملاحظات إضافية">
          {(props) => (
            <textarea
              {...props}
              rows={2}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="معوقات، تأخيرات، أو ملاحظات فنية…"
            />
          )}
        </Field>
      </Modal>
    </>
  )
}
