import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import {
  ArrowUpRight,
  Download,
  FileText,
  Lock,
  Plus,
  Search,
  Square,
  SquareCheckBig,
} from 'lucide-react'
import {
  alertTypeLabel,
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
  downloadIncidentEvidence,
  escalateToOperations,
  getIncident,
  startIncidentInvestigation,
  toggleIncidentAction,
} from '@/api/security'
import { getSecurityFacility as getFacility } from '@/api/security'
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

export function IncidentDetailPage() {
  const { incidentId = '' } = useParams<{ incidentId: string }>()
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const { showToast } = useToast()

  const [noteDraft, setNoteDraft] = useState('')
  const [actionDraft, setActionDraft] = useState('')
  const [captionDraft, setCaptionDraft] = useState('')
  const [evidenceFiles, setEvidenceFiles] = useState<File[]>([])
  const [closeOpen, setCloseOpen] = useState(false)
  const [transferOpen, setTransferOpen] = useState(false)
  const [operationsManagerId, setOperationsManagerId] = useState('')
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

  function mutationError(title: string, error: unknown) {
    showToast({
      tone: 'critical',
      title,
      description: error instanceof Error ? error.message : undefined,
    })
  }

  const addNote = useMutation({
    mutationFn: () => addIncidentNote(incidentId, noteDraft, user.id),
    onSuccess: () => {
      invalidate()
      setNoteDraft('')
      showToast({ tone: 'success', title: 'تمت إضافة الملاحظة' })
    },
    onError: (error) => mutationError('تعذّرت إضافة الملاحظة', error),
  })

  const addAction = useMutation({
    mutationFn: () => addIncidentAction(incidentId, actionDraft),
    onSuccess: () => {
      invalidate()
      setActionDraft('')
      showToast({ tone: 'success', title: 'تمت إضافة الإجراء' })
    },
    onError: (error) => mutationError('تعذّرت إضافة الإجراء', error),
  })

  const toggleAction = useMutation({
    mutationFn: (actionId: string) => toggleIncidentAction(incidentId, actionId),
    onSuccess: () => invalidate(),
    onError: (error) => mutationError('تعذّر تعديل الإجراء', error),
  })

  const addEvidence = useMutation({
    mutationFn: () => addIncidentEvidence(incidentId, evidenceFiles[0] as File),
    onSuccess: () => {
      invalidate()
      setCaptionDraft('')
      setEvidenceFiles([])
      showToast({ tone: 'success', title: 'تمت إضافة الدليل' })
    },
    onError: (error) => mutationError('تعذّرت إضافة الدليل', error),
  })

  const downloadEvidence = useMutation({
    mutationFn: (input: { id: string; filename: string }) =>
      downloadIncidentEvidence(input.id, input.filename),
    onError: (error) => mutationError('تعذّر تنزيل الدليل', error),
  })

  const startInvestigation = useMutation({
    mutationFn: () => startIncidentInvestigation(incidentId, user.id),
    onSuccess: () => {
      invalidate()
      showToast({ tone: 'success', title: 'بدأ التحقيق في الحادث' })
    },
    onError: (error) => mutationError('تعذّر بدء التحقيق', error),
  })

  const escalate = useMutation({
    mutationFn: () => escalateToOperations(incidentId, operationsManagerId),
    onSuccess: () => {
      invalidate()
      setTransferOpen(false)
      setOperationsManagerId('')
      queryClient.invalidateQueries({ queryKey: qk.notifications.all })
      showToast({
        tone: 'warning',
        title: 'تم تحويل الحادث لمدير التشغيل',
        description: 'سيصل إشعار لمدير التشغيل بأن الحادث يتطلب إصلاحاً فنياً.',
      })
    },
    onError: (error) => mutationError('تعذّر تحويل الحادث', error),
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
    onError: (error) => mutationError('تعذّر إغلاق الحادث', error),
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
  const actionsReady = incident.actions.length === 0 || allActionsDone
  const isClosed = incident.status === 'closed'
  const canClose = incident.status === 'investigation' || incident.status === 'transferred'
  const operationsManagers =
    usersQuery.data?.filter((candidate) => candidate.role === 'operations_manager') ?? []

  return (
    <>
      <PageHeader
        title={alertTypeLabel(incident.type)}
        description={incident.description}
        crumbs={[{ label: incident.reference }]}
        actions={
          !isClosed && (
            <>
              {incident.status === 'open' && (
                <Button
                  loading={startInvestigation.isPending}
                  onClick={() => startInvestigation.mutate()}
                >
                  <Search size={15} strokeWidth={2.2} />
                  بدء التحقيق
                </Button>
              )}
              {incident.status === 'investigation' && !incident.escalatedToOperations && (
                <Button variant="ghost" onClick={() => setTransferOpen(true)}>
                  <ArrowUpRight size={15} strokeWidth={2.2} />
                  تحويل لمدير التشغيل
                </Button>
              )}
              {canClose && (
                <Button variant="success" onClick={() => setCloseOpen(true)}>
                  <Lock size={15} strokeWidth={2.2} />
                  إغلاق الحادث
                </Button>
              )}
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
                    <Field
                      label="وصف الدليل"
                      hint="الوصف غير مدعوم في عقد الخلفية الحالي؛ يُحفظ اسم الملف الأصلي."
                    >
                      {(props) => (
                        <input
                          {...props}
                          value={captionDraft}
                          onChange={(event) => setCaptionDraft(event.target.value)}
                          disabled
                          placeholder="صورة الموقع بعد الإخلاء"
                        />
                      )}
                    </Field>
                    <div style={{ marginBottom: 14 }}>
                      <UploadZone
                        accept="image/*,application/pdf"
                        multiple={false}
                        onFilesChange={setEvidenceFiles}
                      />
                    </div>
                    <Button
                      loading={addEvidence.isPending}
                      disabled={evidenceFiles.length === 0}
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
                        <div
                          className={detail.photoMedia}
                          style={{ display: 'grid', placeItems: 'center' }}
                        >
                          <FileText size={30} strokeWidth={1.8} />
                        </div>
                        <figcaption className={detail.photoCaption}>
                          {item.caption}
                          <Button
                            variant="ghost"
                            loading={downloadEvidence.isPending}
                            onClick={() =>
                              downloadEvidence.mutate({
                                id: item.id,
                                filename: item.originalFileName ?? item.caption,
                              })
                            }
                          >
                            <Download size={14} strokeWidth={2.2} />
                            تنزيل
                          </Button>
                        </figcaption>
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
        open={transferOpen}
        onClose={() => setTransferOpen(false)}
        title="تحويل الحادث إلى مدير التشغيل"
        subtitle={incident.reference}
        footer={
          <>
            <Button variant="ghost" onClick={() => setTransferOpen(false)}>
              تراجع
            </Button>
            <Button
              loading={escalate.isPending}
              disabled={!operationsManagerId}
              onClick={() => escalate.mutate()}
            >
              تأكيد التحويل
            </Button>
          </>
        }
      >
        <Field label="مدير التشغيل" required>
          {(props) => (
            <select
              {...props}
              value={operationsManagerId}
              onChange={(event) => setOperationsManagerId(event.target.value)}
            >
              <option value="">اختر مدير التشغيل…</option>
              {operationsManagers.map((manager) => (
                <option key={manager.id} value={manager.id}>
                  {manager.fullName}
                </option>
              ))}
            </select>
          )}
        </Field>
      </Modal>

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
              disabled={finalReport.trim().length < 20 || !actionsReady}
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
              description={`${formatNumber(incident.actions.length - doneActions)} إجراء لم يُعلَّم كمنجز. يجب استكمال جميع الإجراءات قبل الإغلاق.`}
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
