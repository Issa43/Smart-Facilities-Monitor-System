import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { ArrowUpRight, Lock, Plus, Square, SquareCheckBig } from 'lucide-react'
import {
  ALERT_TYPE_LABELS,
  INCIDENT_STATUS_LABELS,
  INCIDENT_STATUS_TONE,
  SEVERITY_LABELS,
  SEVERITY_TONE,
} from '@/types'
import { formatDateTime, formatNumber, formatPercent, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import {
  addIncidentAction,
  addIncidentEvidence,
  addIncidentNote,
  closeIncident,
  escalateToOperations,
  getIncident,
  toggleIncidentAction,
} from '@/api/security'
import { getFacility } from '@/api/operations'
import { listUsers } from '@/api/users'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { Field } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { Panel } from '@/components/ui/Panel/Panel'
import { Tabs } from '@/components/ui/Tabs/Tabs'
import {
  Alert,
  ErrorState,
  ProgressBar,
  SkeletonLines,
  StateCard,
} from '@/components/ui/Feedback/Feedback'
import { DescriptionList, Section, Timeline, UploadZone } from '@/components/ui/Display/Display'
import { ProgressRing } from '@/components/charts/Charts'
import shared from '@/features/shared/Dashboard.module.css'
import detail from '@/features/shared/ProjectDetail.module.css'
import styles from '@/features/operations/pages/WorkOrder.module.css'

const EVIDENCE_GRADIENTS = [
  'linear-gradient(135deg, #DDF3FF, #B8E4FA)',
  'linear-gradient(135deg, #F3E8FF, #DDF3FF)',
  'linear-gradient(135deg, #E4FBF2, #DDF3FF)',
  'linear-gradient(135deg, #FEF6E0, #F3E8FF)',
]

export function IncidentDetailPage() {
  const { incidentId = '' } = useParams<{ incidentId: string }>()
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const { showToast } = useToast()

  const [noteDraft, setNoteDraft] = useState('')
  const [actionDraft, setActionDraft] = useState('')
  const [captionDraft, setCaptionDraft] = useState('')
  const [closeOpen, setCloseOpen] = useState(false)
  const [finalReport, setFinalReport] = useState('')

  const incidentQuery = useQuery({
    queryKey: qk.incidents.detail(incidentId),
    queryFn: () => getIncident(incidentId),
  })
  const incident = incidentQuery.data

  const facilityQuery = useQuery({
    queryKey: qk.facilities.detail(incident?.facilityId ?? ''),
    queryFn: () => getFacility(incident?.facilityId as string),
    enabled: Boolean(incident?.facilityId),
  })
  const usersQuery = useQuery({ queryKey: qk.users.all, queryFn: listUsers })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: qk.incidents.all })
    queryClient.invalidateQueries({ queryKey: qk.stats.security })
  }

  const addNote = useMutation({
    mutationFn: () => addIncidentNote(incidentId, noteDraft, user.id),
    onSuccess: () => {
      invalidate()
      setNoteDraft('')
      showToast({ tone: 'success', title: 'تمت إضافة الملاحظة' })
    },
  })

  const addAction = useMutation({
    mutationFn: () => addIncidentAction(incidentId, actionDraft),
    onSuccess: () => {
      invalidate()
      setActionDraft('')
      showToast({ tone: 'success', title: 'تمت إضافة الإجراء' })
    },
  })

  const toggleAction = useMutation({
    mutationFn: (actionId: string) => toggleIncidentAction(incidentId, actionId),
    onSuccess: () => invalidate(),
  })

  const addEvidence = useMutation({
    mutationFn: () =>
      addIncidentEvidence(
        incidentId,
        captionDraft,
        EVIDENCE_GRADIENTS[(incident?.evidence.length ?? 0) % EVIDENCE_GRADIENTS.length] as string,
      ),
    onSuccess: () => {
      invalidate()
      setCaptionDraft('')
      showToast({ tone: 'success', title: 'تمت إضافة الدليل' })
    },
  })

  const escalate = useMutation({
    mutationFn: () => escalateToOperations(incidentId),
    onSuccess: () => {
      invalidate()
      queryClient.invalidateQueries({ queryKey: qk.notifications.all })
      showToast({
        tone: 'warning',
        title: 'تم تحويل الحادث لمدير التشغيل',
        description: 'سيصل إشعار لمدير التشغيل بأن الحادث يتطلب إصلاحاً فنياً.',
      })
    },
  })

  const close = useMutation({
    mutationFn: () => closeIncident(incidentId, finalReport, user.id),
    onSuccess: (updated) => {
      invalidate()
      setCloseOpen(false)
      showToast({
        tone: 'success',
        title: 'تم إغلاق الحادث',
        description: `${updated.reference} — تم تسجيل تاريخ ووقت الإغلاق والتقرير النهائي.`,
      })
    },
  })

  if (incidentQuery.isError) return <ErrorState error={incidentQuery.error} />
  if (incidentQuery.isPending || !incident) {
    return (
      <Panel>
        <SkeletonLines count={7} />
      </Panel>
    )
  }

  const userName = (id: string | null) =>
    id ? (usersQuery.data?.find((u) => u.id === id)?.fullName ?? '—') : '—'

  const doneActions = incident.actions.filter((action) => action.done).length
  const actionProgress =
    incident.actions.length === 0 ? 0 : Math.round((doneActions / incident.actions.length) * 100)
  const allActionsDone = incident.actions.length > 0 && doneActions === incident.actions.length
  const isClosed = incident.status === 'closed'

  return (
    <>
      <PageHeader
        title={ALERT_TYPE_LABELS[incident.type]}
        description={incident.description}
        crumbs={[{ label: incident.reference }]}
        actions={
          !isClosed && (
            <>
              {!incident.escalatedToOperations && (
                <Button
                  variant="ghost"
                  loading={escalate.isPending}
                  onClick={() => escalate.mutate()}
                >
                  <ArrowUpRight size={15} strokeWidth={2.2} />
                  تحويل لمدير التشغيل
                </Button>
              )}
              <Button variant="success" onClick={() => setCloseOpen(true)}>
                <Lock size={15} strokeWidth={2.2} />
                إغلاق الحادث
              </Button>
            </>
          )
        }
      />

      {isClosed && (
        <Section>
          <Alert
            tone="success"
            title={`تم إغلاق الحادث في ${formatDateTime(incident.closedAt)}`}
            description={`أغلقه: ${userName(incident.closedById)}`}
          />
        </Section>
      )}

      {incident.escalatedToOperations && !isClosed && (
        <Section>
          <Alert
            tone="warning"
            title="الحادث محوّل لمدير التشغيل"
            description="يتطلب هذا الحادث إصلاحاً فنياً. تم إشعار مدير التشغيل، ويمكن متابعة أمر الصيانة المرتبط من قسم التشغيل."
          />
        </Section>
      )}

      <Section>
        <div className={detail.hero}>
          <ProgressRing percent={actionProgress} size={128} label="الإجراءات" />
          <div className={detail.heroBody}>
            <div className={detail.heroTop}>
              <Badge tone={INCIDENT_STATUS_TONE[incident.status]}>
                {INCIDENT_STATUS_LABELS[incident.status]}
              </Badge>
              <Badge tone={SEVERITY_TONE[incident.severity]}>
                خطورة {SEVERITY_LABELS[incident.severity]}
              </Badge>
            </div>
            <DescriptionList
              items={[
                { label: 'رقم الحادث', value: <span className="mono">{incident.reference}</span> },
                { label: 'الموقع', value: incident.location },
                { label: 'المنشأة', value: facilityQuery.data?.name ?? '—' },
                { label: 'المسؤول عن المتابعة', value: userName(incident.assigneeId) },
                { label: 'تاريخ الإنشاء', value: formatDateTime(incident.createdAt) },
                {
                  label: 'الإجراءات المنجزة',
                  value: `${formatNumber(doneActions)} من ${formatNumber(incident.actions.length)}`,
                },
              ]}
            />
          </div>
        </div>
      </Section>

      <Tabs
        tabs={[
          /* ---------- Timeline ---------- */
          {
            id: 'timeline',
            label: 'التسلسل الزمني',
            content: (
              <Panel title="مسار الحادث">
                <Timeline
                  entries={[
                    {
                      id: 'created',
                      tone: 'critical',
                      title: 'تسجيل الحادث',
                      body: incident.description,
                      meta: formatDateTime(incident.createdAt),
                    },
                    ...incident.notes.map((note) => ({
                      id: note.id,
                      tone: 'info' as const,
                      title: `ملاحظة من ${userName(note.authorId)}`,
                      body: note.body,
                      meta: formatRelative(note.createdAt),
                    })),
                    ...incident.actions
                      .filter((action) => action.done)
                      .map((action) => ({
                        id: action.id,
                        tone: 'success' as const,
                        title: `إجراء منجز: ${action.label}`,
                        meta: action.takenAt ? formatDateTime(action.takenAt) : '',
                      })),
                    ...(incident.escalatedToOperations
                      ? [
                          {
                            id: 'escalated',
                            tone: 'warning' as const,
                            title: 'تحويل الحادث لمدير التشغيل',
                            body: 'يتطلب الحادث إصلاحاً فنياً من فريق التشغيل.',
                          },
                        ]
                      : []),
                    ...(incident.closedAt
                      ? [
                          {
                            id: 'closed',
                            tone: 'success' as const,
                            title: 'إغلاق الحادث',
                            body: incident.finalReport ?? undefined,
                            meta: `${formatDateTime(incident.closedAt)} · ${userName(incident.closedById)}`,
                          },
                        ]
                      : []),
                  ]}
                />
              </Panel>
            ),
          },

          /* ---------- Investigation notes ---------- */
          {
            id: 'notes',
            label: 'ملاحظات التحقيق',
            count: incident.notes.length,
            content: (
              <Panel title="ملاحظات التحقيق" subtitle="كل ملاحظة تُحفظ باسم كاتبها ووقتها">
                {!isClosed && (
                  <div style={{ marginBottom: 20 }}>
                    <Field label="إضافة ملاحظة" hint="10 أحرف على الأقل">
                      {(props) => (
                        <textarea
                          {...props}
                          rows={3}
                          value={noteDraft}
                          onChange={(event) => setNoteDraft(event.target.value)}
                          placeholder="ما تم رصده أو التحقق منه…"
                        />
                      )}
                    </Field>
                    <Button
                      loading={addNote.isPending}
                      disabled={noteDraft.trim().length < 10}
                      onClick={() => addNote.mutate()}
                    >
                      <Plus size={15} strokeWidth={2.2} />
                      إضافة الملاحظة
                    </Button>
                  </div>
                )}

                {incident.notes.length === 0 ? (
                  <StateCard bare title="لا توجد ملاحظات" description="أضف أول ملاحظة تحقيق." />
                ) : (
                  <Timeline
                    entries={incident.notes
                      .slice()
                      .reverse()
                      .map((note) => ({
                        id: note.id,
                        tone: 'info',
                        title: userName(note.authorId),
                        body: note.body,
                        meta: formatDateTime(note.createdAt),
                      }))}
                  />
                )}
              </Panel>
            ),
          },

          /* ---------- Evidence ---------- */
          {
            id: 'evidence',
            label: 'الأدلة والمرفقات',
            count: incident.evidence.length,
            content: (
              <Panel title="الأدلة المرفقة">
                {!isClosed && (
                  <div style={{ marginBottom: 20 }}>
                    <Field label="وصف الدليل" hint="اذكر ما تُظهره الصورة أو الملف">
                      {(props) => (
                        <input
                          {...props}
                          value={captionDraft}
                          onChange={(event) => setCaptionDraft(event.target.value)}
                          placeholder="صورة الموقع بعد الإخلاء"
                        />
                      )}
                    </Field>
                    <div style={{ marginBottom: 14 }}>
                      <UploadZone accept="image/*,application/pdf" />
                    </div>
                    <Button
                      loading={addEvidence.isPending}
                      disabled={captionDraft.trim().length < 5}
                      onClick={() => addEvidence.mutate()}
                    >
                      <Plus size={15} strokeWidth={2.2} />
                      إضافة الدليل
                    </Button>
                  </div>
                )}

                {incident.evidence.length === 0 ? (
                  <StateCard bare title="لا توجد أدلة مرفقة" />
                ) : (
                  <div className={detail.photoGrid}>
                    {incident.evidence.map((item) => (
                      <figure key={item.id} className={detail.photo}>
                        <div className={detail.photoMedia} style={{ background: item.gradient }} />
                        <figcaption className={detail.photoCaption}>{item.caption}</figcaption>
                      </figure>
                    ))}
                  </div>
                )}
              </Panel>
            ),
          },

          /* ---------- Response actions ---------- */
          {
            id: 'actions',
            label: 'إجراءات الاستجابة',
            count: incident.actions.length,
            content: (
              <Panel
                title="إجراءات الاستجابة"
                subtitle="اضغط على أي إجراء لتعليمه كمنجز"
                actions={
                  <Badge tone={allActionsDone ? 'success' : 'warning'}>
                    {formatPercent(actionProgress)}
                  </Badge>
                }
              >
                {incident.actions.length > 0 && (
                  <div style={{ marginBottom: 18 }}>
                    <ProgressBar value={actionProgress} label="الإجراءات المنجزة" />
                  </div>
                )}

                {!isClosed && (
                  <div
                    style={{ marginBottom: 20, display: 'flex', gap: 10, alignItems: 'flex-end' }}
                  >
                    <div style={{ flex: 1 }}>
                      <Field label="إضافة إجراء">
                        {(props) => (
                          <input
                            {...props}
                            value={actionDraft}
                            onChange={(event) => setActionDraft(event.target.value)}
                            placeholder="إخلاء المنطقة المتأثرة"
                          />
                        )}
                      </Field>
                    </div>
                    <div style={{ marginBottom: 16 }}>
                      <Button
                        loading={addAction.isPending}
                        disabled={actionDraft.trim().length < 3}
                        onClick={() => addAction.mutate()}
                      >
                        <Plus size={15} strokeWidth={2.2} />
                        إضافة
                      </Button>
                    </div>
                  </div>
                )}

                {incident.actions.length === 0 ? (
                  <StateCard bare title="لا توجد إجراءات" description="أضف أول إجراء استجابة." />
                ) : (
                  <ul className={styles.tasks}>
                    {incident.actions.map((action) => (
                      <li key={action.id}>
                        <button
                          type="button"
                          className={action.done ? styles.taskDone : styles.task}
                          onClick={() => toggleAction.mutate(action.id)}
                          disabled={isClosed || toggleAction.isPending}
                          aria-pressed={action.done}
                        >
                          {action.done ? (
                            <SquareCheckBig size={17} strokeWidth={2.2} />
                          ) : (
                            <Square size={17} strokeWidth={2} />
                          )}
                          <span>{action.label}</span>
                          {action.takenAt && (
                            <span style={{ marginInlineStart: 'auto', fontSize: 11, opacity: 0.8 }}>
                              {formatRelative(action.takenAt)}
                            </span>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            ),
          },

          /* ---------- Resolution summary ---------- */
          {
            id: 'resolution',
            label: 'التقرير النهائي',
            content: (
              <Panel title="ملخص المعالجة">
                {incident.finalReport ? (
                  <>
                    <p className={shared.hint} style={{ fontSize: 13, lineHeight: 2 }}>
                      {incident.finalReport}
                    </p>
                    <div style={{ marginTop: 20 }}>
                      <DescriptionList
                        items={[
                          { label: 'تاريخ الإغلاق', value: formatDateTime(incident.closedAt) },
                          { label: 'أغلق الحادث', value: userName(incident.closedById) },
                          {
                            label: 'إجمالي الإجراءات',
                            value: formatNumber(incident.actions.length),
                          },
                          {
                            label: 'الأدلة المرفقة',
                            value: formatNumber(incident.evidence.length),
                          },
                        ]}
                      />
                    </div>
                  </>
                ) : (
                  <StateCard
                    bare
                    title="لم يُكتب التقرير النهائي بعد"
                    description="يُكتب التقرير النهائي عند إغلاق الحادث، ويوثّق ما حدث والإجراءات المتخذة والتوصيات."
                    action={
                      !isClosed && (
                        <Button variant="success" onClick={() => setCloseOpen(true)}>
                          <Lock size={15} strokeWidth={2.2} />
                          إغلاق الحادث وكتابة التقرير
                        </Button>
                      )
                    }
                  />
                )}
              </Panel>
            ),
          },
        ]}
      />

      <Modal
        open={closeOpen}
        onClose={() => setCloseOpen(false)}
        title="إغلاق الحادث"
        subtitle={incident.reference}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCloseOpen(false)}>
              إلغاء
            </Button>
            <Button
              variant="success"
              loading={close.isPending}
              disabled={finalReport.trim().length < 20}
              onClick={() => close.mutate()}
            >
              تأكيد الإغلاق
            </Button>
          </>
        }
      >
        {!allActionsDone && incident.actions.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <Alert
              tone="warning"
              title="إجراءات غير مكتملة"
              description={`${formatNumber(incident.actions.length - doneActions)} إجراء لم يُعلَّم كمنجز. يُفضّل استكمالها قبل الإغلاق.`}
            />
          </div>
        )}

        <Field
          label="التقرير النهائي"
          hint="20 حرفاً على الأقل — اذكر ما حدث، الإجراءات المتخذة، والتوصيات"
          required
        >
          {(props) => (
            <textarea
              {...props}
              rows={6}
              value={finalReport}
              onChange={(event) => setFinalReport(event.target.value)}
              placeholder="ملخص الحادث، سببه، الإجراءات المتخذة، والتوصيات لمنع تكراره…"
            />
          )}
        </Field>

        <p style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.9 }}>
          سيسجّل النظام تاريخ ووقت الإغلاق واسمك كمن أغلق الحادث، وستتحول حالته إلى «مغلق».
        </p>
      </Modal>
    </>
  )
}
