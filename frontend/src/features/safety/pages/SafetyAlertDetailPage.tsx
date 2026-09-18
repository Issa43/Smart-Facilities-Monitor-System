import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import type { SafetyAction, SafetyAlert, SafetyWorkflowAction } from '@/types'
import {
  HAZARD_ALERT_LEVEL_LABELS,
  HAZARD_PROVIDER_LABELS,
  HAZARD_PROVIDER_STATUS_LABELS,
  HAZARD_TYPE_LABELS,
  SAFETY_ACTIONS,
  SAFETY_ACTION_LABELS,
  SAFETY_ALERT_STATUS_LABELS,
  SAFETY_ALERT_STATUS_TONE,
  SAFETY_DECISION_REQUIRING_NOTES,
  SAFETY_NOTES_MAX_LENGTH,
  SAFETY_PROJECT_STATUS_LABELS,
  SAFETY_WORKFLOW_ACTION_LABELS,
  SEVERITY_LABELS,
  SEVERITY_TONE,
} from '@/types'
import { formatDateTime, formatDecimal } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import {
  acknowledgeSafetyAlert,
  closeSafetyAlert,
  decideSafetyAlert,
  dismissSafetyAlert,
  getSafetyAlert,
} from '@/api/safety'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { Field } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { Panel } from '@/components/ui/Panel/Panel'
import { Alert, ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { DescriptionList, Section, SplitGrid } from '@/components/ui/Display/Display'
import shared from '@/features/shared/Dashboard.module.css'
import { DecisionWorkflowPanel } from '../DecisionWorkflowPanel'
import { presentSafetyError, safeSourceUrl } from '../safetyErrors'
import styles from '../Safety.module.css'

type OpenDialog = 'decide' | 'dismiss' | 'close' | null

const dash = (value: string | null | undefined) => (value ? value : '—')
const decimal = (value: string | null, unit = '') =>
  value === null ? '—' : `${formatDecimal(Number(value))}${unit}`
const when = (value: string | null) => (value ? formatDateTime(value) : '—')
/** Provider magnitudes are shown exactly as reported (no rounding). */
const exact = (value: string | null) => (value === null ? '—' : String(Number(value)))

/** The route branch (construction/operations) only decides which URL renders
 *  this page; the breadcrumb and back link come from the role's nav config. */
export function SafetyAlertDetailPage() {
  const { alertId = '' } = useParams<{ alertId: string }>()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [dialog, setDialog] = useState<OpenDialog>(null)
  const [decision, setDecision] = useState<SafetyAction | ''>('')
  const [decisionNotes, setDecisionNotes] = useState('')
  const [dismissReason, setDismissReason] = useState('')
  const [closeNotes, setCloseNotes] = useState('')

  const alertQuery = useQuery({
    queryKey: qk.safety.alertDetail(alertId),
    queryFn: () => getSafetyAlert(alertId),
    enabled: Boolean(alertId),
    retry: false,
  })

  function applyUpdated(updated: SafetyAlert, message: string) {
    // The response is the authoritative new state; only list pages need refreshing.
    queryClient.setQueryData(qk.safety.alertDetail(updated.id), updated)
    void queryClient.invalidateQueries({ queryKey: qk.safety.alertLists })
    setDialog(null)
    showToast({ tone: 'success', title: message })
  }

  function handleError(error: unknown) {
    const presentation = presentSafetyError(error)
    showToast({
      tone: 'critical',
      title: presentation.title,
      description: presentation.description,
    })
    if (presentation.reconcile) {
      void queryClient.invalidateQueries({ queryKey: qk.safety.alertDetail(alertId) })
      void queryClient.invalidateQueries({ queryKey: qk.safety.alertLists })
    }
  }

  const acknowledge = useMutation({
    mutationFn: () => acknowledgeSafetyAlert(alertId),
    onSuccess: (updated) => applyUpdated(updated, 'تم إقرار الاطلاع على الإنذار'),
    onError: handleError,
  })
  const decide = useMutation({
    mutationFn: () =>
      decideSafetyAlert(alertId, { decision: decision as SafetyAction, notes: decisionNotes }),
    onSuccess: (updated) => applyUpdated(updated, 'تم تسجيل القرار'),
    onError: handleError,
  })
  const dismiss = useMutation({
    mutationFn: () => dismissSafetyAlert(alertId, dismissReason),
    onSuccess: (updated) => applyUpdated(updated, 'تم استبعاد الإنذار'),
    onError: handleError,
  })
  const close = useMutation({
    mutationFn: () => closeSafetyAlert(alertId, closeNotes),
    onSuccess: (updated) => applyUpdated(updated, 'تم إغلاق الإنذار'),
    onError: handleError,
  })
  const busy = acknowledge.isPending || decide.isPending || dismiss.isPending || close.isPending

  // PageHeader already renders the linked "الإنذارات والسلامة" nav crumb; only
  // the page-specific trailing crumb belongs here.
  const listCrumb = [{ label: 'تفاصيل الإنذار' }]

  if (alertQuery.isPending) {
    return (
      <>
        <PageHeader title="تفاصيل إنذار السلامة" crumbs={listCrumb} />
        <Section>
          <Panel>
            <SkeletonLines count={8} />
          </Panel>
        </Section>
      </>
    )
  }

  if (alertQuery.isError) {
    const presentation = presentSafetyError(alertQuery.error)
    return (
      <>
        <PageHeader title="تفاصيل إنذار السلامة" crumbs={listCrumb} />
        <Section>
          {presentation.kind === 'forbidden' || presentation.kind === 'not_found' ? (
            <StateCard
              tone="critical"
              title={presentation.title}
              description={presentation.description}
            />
          ) : (
            <ErrorState
              error={new Error(presentation.description)}
              onRetry={() => alertQuery.refetch()}
            />
          )}
        </Section>
      </>
    )
  }

  const alert = alertQuery.data
  const hazard = alert.hazardEvent
  const available = new Set<SafetyWorkflowAction>(alert.availableActions)
  const sourceUrl = safeSourceUrl(hazard.sourceUrl)
  const notesRequired = decision === SAFETY_DECISION_REQUIRING_NOTES
  const decisionInvalid =
    !decision ||
    (notesRequired && !decisionNotes.trim()) ||
    decisionNotes.length > SAFETY_NOTES_MAX_LENGTH

  function openDecide() {
    setDecision(alert.decision ?? '')
    setDecisionNotes(alert.decisionNotes ?? '')
    setDialog('decide')
  }

  return (
    <>
      <PageHeader
        title={hazard.title}
        description={`${HAZARD_TYPE_LABELS[alert.hazardType]} — ${alert.project.name}`}
        crumbs={[{ label: alert.project.name }]}
        actions={
          available.size > 0 && (
            <div className={styles.actionBar}>
              {available.has('acknowledge') && (
                <Button
                  loading={acknowledge.isPending}
                  disabled={busy}
                  onClick={() => acknowledge.mutate()}
                >
                  {SAFETY_WORKFLOW_ACTION_LABELS.acknowledge}
                </Button>
              )}
              {available.has('decide') && (
                <Button variant="ghost" disabled={busy} onClick={openDecide}>
                  {SAFETY_WORKFLOW_ACTION_LABELS.decide}
                </Button>
              )}
              {available.has('close') && (
                <Button variant="ghost" disabled={busy} onClick={() => setDialog('close')}>
                  {SAFETY_WORKFLOW_ACTION_LABELS.close}
                </Button>
              )}
              {available.has('dismiss') && (
                <Button variant="critical" disabled={busy} onClick={() => setDialog('dismiss')}>
                  {SAFETY_WORKFLOW_ACTION_LABELS.dismiss}
                </Button>
              )}
            </div>
          )
        }
      />

      <Section>
        <Alert
          tone="info"
          title="التوصية استرشادية"
          description="يقترح النظام إجراءً بناءً على سياسة السلامة، ولا يوقف الأعمال أو يُخلي المواقع أو يراسل العمال تلقائياً. القرار للمدير المسؤول."
        />
      </Section>

      {/* Sits directly under the hazard summary: the decision awaiting this
          viewer is the reason they opened the page. */}
      <Section>
        <DecisionWorkflowPanel alert={alert} />
      </Section>

      {alert.hazardWithdrawnAt && (
        <Section>
          <Alert
            tone="warning"
            title="أفاد المصدر بسحب هذا الحدث"
            description={`سُجّل السحب في ${formatDateTime(alert.hazardWithdrawnAt)}. يبقى الإنذار قائماً حتى يُغلقه أو يستبعده المدير المسؤول.`}
          />
        </Section>
      )}

      {alert.escalatedAt && (
        <Section>
          <Alert
            tone="warning"
            title="تم تصعيد خطورة الإنذار"
            description={`رُفعت الخطورة بعد تحديث من المصدر في ${formatDateTime(alert.escalatedAt)}.`}
          />
        </Section>
      )}

      <Section>
        <Panel title="الإنذار">
          <div className={styles.flags} style={{ marginBottom: 14 }}>
            <Badge tone={SEVERITY_TONE[alert.severity]}>
              خطورة {SEVERITY_LABELS[alert.severity]}
            </Badge>
            <Badge tone={SAFETY_ALERT_STATUS_TONE[alert.status]}>
              {SAFETY_ALERT_STATUS_LABELS[alert.status]}
            </Badge>
          </div>
          <DescriptionList
            items={[
              { label: 'رقم الإنذار', value: <span className="mono">{alert.id}</span> },
              { label: 'نوع الخطر', value: HAZARD_TYPE_LABELS[alert.hazardType] },
              { label: 'المسافة عن المشروع', value: decimal(alert.distanceKm, ' كم') },
              { label: 'الإجراء الموصى به', value: SAFETY_ACTION_LABELS[alert.recommendedAction] },
              { label: 'قاعدة السياسة', value: <span className="mono">{alert.ruleCode}</span> },
              { label: 'إصدار السياسة', value: String(alert.policyVersion) },
              { label: 'تاريخ الإنشاء', value: formatDateTime(alert.createdAt) },
              { label: 'آخر تحديث', value: formatDateTime(alert.updatedAt) },
            ]}
          />
        </Panel>
      </Section>

      <SplitGrid even>
        <Panel title="المشروع" subtitle="إحداثيات المشروع كما سُجّلت عند إنشاء الإنذار">
          <DescriptionList
            single
            items={[
              { label: 'اسم المشروع', value: alert.project.name },
              { label: 'الموقع', value: dash(alert.project.location) },
              { label: 'حالة المشروع', value: SAFETY_PROJECT_STATUS_LABELS[alert.project.status] },
              {
                label: 'الإحداثيات',
                value: (
                  <span className="mono">{`${alert.projectLatitude}, ${alert.projectLongitude}`}</span>
                ),
              },
            ]}
          />
        </Panel>

        <Panel title="الحدث الخارجي" subtitle="بيانات مُطبّعة من المصدر للاطلاع فقط">
          <DescriptionList
            single
            items={[
              { label: 'المصدر', value: HAZARD_PROVIDER_LABELS[hazard.provider] },
              {
                label: 'معرّف الحدث لدى المصدر',
                value: <span className="mono">{hazard.providerEventId}</span>,
              },
              {
                label: 'حالة الحدث لدى المصدر',
                value: HAZARD_PROVIDER_STATUS_LABELS[hazard.providerStatus],
              },
              {
                label: 'مستوى التنبيه',
                value: hazard.alertLevel ? HAZARD_ALERT_LEVEL_LABELS[hazard.alertLevel] : '—',
              },
              { label: 'وصف الخطورة لدى المصدر', value: dash(hazard.providerSeverity) },
              { label: 'القوة', value: exact(hazard.magnitude) },
              { label: 'العمق', value: decimal(hazard.depthKm, ' كم') },
              { label: 'نصف القطر', value: decimal(hazard.radiusKm, ' كم') },
              {
                label: 'إحداثيات الحدث',
                value: <span className="mono">{`${hazard.latitude}, ${hazard.longitude}`}</span>,
              },
              { label: 'وقت وقوع الحدث', value: formatDateTime(hazard.occurredAt) },
              { label: 'آخر تحديث من المصدر', value: formatDateTime(hazard.providerUpdatedAt) },
              { label: 'بداية الصلاحية', value: when(hazard.validFrom) },
              { label: 'نهاية الصلاحية', value: when(hazard.validUntil) },
              { label: 'رقم المراجعة', value: String(hazard.revision) },
              {
                label: 'صفحة الحدث لدى المصدر',
                value: sourceUrl ? (
                  <a href={sourceUrl} target="_blank" rel="noopener noreferrer nofollow">
                    فتح صفحة المصدر (موقع خارجي)
                  </a>
                ) : (
                  '—'
                ),
              },
            ]}
          />
        </Panel>
      </SplitGrid>

      <Section>
        <Panel title="القرار وسجل المعالجة">
          <DescriptionList
            items={[
              { label: 'أقرّ الاطلاع', value: alert.acknowledgedBy?.fullName ?? '—' },
              { label: 'وقت الإقرار', value: when(alert.acknowledgedAt) },
              {
                label: 'القرار',
                value: alert.decision ? SAFETY_ACTION_LABELS[alert.decision] : '—',
              },
              { label: 'متخذ القرار', value: alert.decidedBy?.fullName ?? '—' },
              { label: 'وقت القرار', value: when(alert.decidedAt) },
              {
                label: 'ملاحظات القرار',
                value: <span className={styles.notes}>{dash(alert.decisionNotes)}</span>,
              },
              { label: 'أُغلق/استُبعد بواسطة', value: alert.resolvedBy?.fullName ?? '—' },
              { label: 'وقت الإغلاق/الاستبعاد', value: when(alert.resolvedAt) },
              {
                label: 'ملاحظات الإغلاق/سبب الاستبعاد',
                value: <span className={styles.notes}>{dash(alert.resolutionNotes)}</span>,
              },
            ]}
          />
          {available.size === 0 && (
            <p className={shared.hint} style={{ marginTop: 14 }}>
              لا توجد إجراءات متاحة لك على هذا الإنذار في حالته الحالية.
            </p>
          )}
        </Panel>
      </Section>

      <Modal
        open={dialog === 'decide'}
        onClose={() => setDialog(null)}
        title="تسجيل قرار السلامة"
        subtitle="يُسجَّل قرارك في سجل التدقيق. لا ينفّذ النظام أي إجراء ميداني تلقائياً."
        footer={
          <>
            <Button variant="ghost" onClick={() => setDialog(null)}>
              إلغاء
            </Button>
            <Button
              loading={decide.isPending}
              disabled={decisionInvalid}
              onClick={() => decide.mutate()}
            >
              حفظ القرار
            </Button>
          </>
        }
      >
        <Field label="القرار" required>
          {(props) => (
            <select
              {...props}
              value={decision}
              onChange={(event) => setDecision(event.target.value as SafetyAction | '')}
            >
              <option value="">اختر القرار…</option>
              {SAFETY_ACTIONS.map((value) => (
                <option key={value} value={value}>
                  {SAFETY_ACTION_LABELS[value]}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field
          label="ملاحظات"
          required={notesRequired}
          hint={notesRequired ? 'الملاحظات مطلوبة عند اختيار «إجراء آخر».' : 'اختيارية.'}
        >
          {(props) => (
            <textarea
              {...props}
              rows={4}
              maxLength={SAFETY_NOTES_MAX_LENGTH}
              value={decisionNotes}
              onChange={(event) => setDecisionNotes(event.target.value)}
            />
          )}
        </Field>
      </Modal>

      <Modal
        open={dialog === 'dismiss'}
        onClose={() => setDialog(null)}
        title="استبعاد الإنذار"
        subtitle="استخدم الاستبعاد فقط إذا لم يكن الإنذار ذا صلة بالمشروع. سبب الاستبعاد مطلوب."
        footer={
          <>
            <Button variant="ghost" onClick={() => setDialog(null)}>
              إلغاء
            </Button>
            <Button
              variant="critical"
              loading={dismiss.isPending}
              disabled={!dismissReason.trim()}
              onClick={() => dismiss.mutate()}
            >
              تأكيد الاستبعاد
            </Button>
          </>
        }
      >
        <Field label="سبب الاستبعاد" required>
          {(props) => (
            <textarea
              {...props}
              rows={4}
              maxLength={SAFETY_NOTES_MAX_LENGTH}
              value={dismissReason}
              onChange={(event) => setDismissReason(event.target.value)}
            />
          )}
        </Field>
      </Modal>

      <Modal
        open={dialog === 'close'}
        onClose={() => setDialog(null)}
        title="إغلاق الإنذار"
        subtitle="يُغلق الإنذار نهائياً بعد تنفيذ القرار المسجّل."
        footer={
          <>
            <Button variant="ghost" onClick={() => setDialog(null)}>
              إلغاء
            </Button>
            <Button loading={close.isPending} onClick={() => close.mutate()}>
              تأكيد الإغلاق
            </Button>
          </>
        }
      >
        <Field label="ملاحظات الإغلاق" hint="اختيارية.">
          {(props) => (
            <textarea
              {...props}
              rows={4}
              maxLength={SAFETY_NOTES_MAX_LENGTH}
              value={closeNotes}
              onChange={(event) => setCloseNotes(event.target.value)}
            />
          )}
        </Field>
      </Modal>
    </>
  )
}
