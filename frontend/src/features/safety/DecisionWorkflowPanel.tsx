import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ShieldCheck, Wrench } from 'lucide-react'
import type {
  SafetyAction,
  SafetyAlert,
  SafetyDecisionType,
  SafetyOpenProposal,
} from '@/types'
import {
  SAFETY_ACTIONS,
  SAFETY_ACTION_LABELS,
  SAFETY_DECISION_TYPE_LABELS,
  SAFETY_NOTES_MAX_LENGTH,
  SAFETY_PROPOSAL_STATUS_LABELS,
  SAFETY_PROPOSAL_STATUS_TONE,
} from '@/types'
import { formatDateTime } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import {
  approveSafetyProposal,
  createSafetyProposal,
  rejectSafetyProposal,
} from '@/api/safety'
import { useToast } from '@/context/ToastContext'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { Field } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { Panel } from '@/components/ui/Panel/Panel'
import { Alert, StateCard } from '@/components/ui/Feedback/Feedback'
import { presentSafetyError } from './safetyErrors'
import styles from './Safety.module.css'

const TYPE_ICON: Record<SafetyDecisionType, typeof ShieldCheck> = {
  worker_protection: ShieldCheck,
  asset_protection: Wrench,
}

/** What approving each kind of proposal actually causes, stated plainly so a
 *  General Manager is never guessing at the consequence of their click. */
const APPROVAL_CONSEQUENCE: Record<SafetyDecisionType, string> = {
  worker_protection:
    'بالموافقة يعتمد القرار ويرسله نظام SFLMS تلقائياً عبر بوت تيليجرام الرسمي إلى قناة المشروع المتأثر فقط. لا حاجة لأي إرسال يدوي.',
  asset_protection:
    'بالموافقة يُعتمد القرار ويُوثَّق في سجل التدقيق. لا يتم إيقاف أي أصل تلقائياً، ولا يُرسل أي إشعار للعاملين.',
}

/** Worker protection is one action: approve *and* send. Asset protection has
 *  no outbound step, so its button says only what it does. */
const APPROVE_LABEL: Record<SafetyDecisionType, string> = {
  worker_protection: 'موافقة وإرسال القرار',
  asset_protection: 'اعتماد القرار',
}

/** The proposal's effective window, or '' when it has none. */
function windowLabel(proposal: SafetyOpenProposal): string {
  const from = proposal.effectiveFrom ? formatDateTime(proposal.effectiveFrom) : ''
  const to = proposal.effectiveUntil ? formatDateTime(proposal.effectiveUntil) : ''
  if (from && to) return `${from} — ${to}`
  if (from) return `من ${from}`
  if (to) return `حتى ${to}`
  return ''
}

type Ruling = { proposal: SafetyOpenProposal; verdict: 'approve' | 'reject' } | null

interface Props {
  alert: SafetyAlert
}

/**
 * The human decision workflow on one safety alert.
 *
 * Renders only what the server says this viewer may do: `availableProposalTypes`
 * drives the proposal forms and each proposal's own `canReview` drives the
 * Approve/Reject controls. No role name is consulted here, and hiding a control
 * is presentation only -- the API refuses the action regardless.
 */
export function DecisionWorkflowPanel({ alert }: Props) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [proposing, setProposing] = useState<SafetyDecisionType | null>(null)
  const [ruling, setRuling] = useState<Ruling>(null)
  const [action, setAction] = useState<SafetyAction | ''>('')
  const [notes, setNotes] = useState('')
  const [reason, setReason] = useState('')
  const [effectiveFrom, setEffectiveFrom] = useState('')
  const [effectiveUntil, setEffectiveUntil] = useState('')
  const [workerScope, setWorkerScope] = useState('')

  function refresh(message: string) {
    void queryClient.invalidateQueries({ queryKey: qk.safety.alertDetail(alert.id) })
    void queryClient.invalidateQueries({ queryKey: qk.safety.alertLists })
    setProposing(null)
    setRuling(null)
    setAction('')
    setNotes('')
    setReason('')
    setEffectiveFrom('')
    setEffectiveUntil('')
    setWorkerScope('')
    showToast({ tone: 'success', title: message })
  }

  function onError(error: unknown) {
    const presentation = presentSafetyError(error)
    showToast({
      tone: 'critical',
      title: presentation.title,
      description: presentation.description,
    })
    if (presentation.reconcile) {
      void queryClient.invalidateQueries({ queryKey: qk.safety.alertDetail(alert.id) })
    }
  }

  const propose = useMutation({
    mutationFn: () =>
      createSafetyProposal(alert.id, {
        decisionType: proposing as SafetyDecisionType,
        proposedAction: action as SafetyAction,
        notes,
        // A datetime-local value is wall-clock; send it as an instant.
        effectiveFrom: effectiveFrom ? new Date(effectiveFrom).toISOString() : null,
        effectiveUntil: effectiveUntil ? new Date(effectiveUntil).toISOString() : null,
        workerScope,
      }),
    onSuccess: () => refresh('تم إرسال الاقتراح إلى المدير العام'),
    onError,
  })

  const decide = useMutation({
    mutationFn: () => {
      if (!ruling) throw new Error('no ruling')
      return ruling.verdict === 'approve'
        ? approveSafetyProposal(ruling.proposal.id, notes)
        : rejectSafetyProposal(ruling.proposal.id, reason)
    },
    onSuccess: () =>
      refresh(
        ruling?.verdict !== 'approve'
          ? 'تم رفض الاقتراح'
          : ruling.proposal.decisionType === 'worker_protection'
            ? 'تم اعتماد القرار وإرساله إلى قناة المشروع'
            : 'تم اعتماد القرار',
      ),
    onError,
  })

  const busy = propose.isPending || decide.isPending
  const hasOpen = alert.openProposals.length > 0
  const canPropose = alert.availableProposalTypes.length > 0

  if (!hasOpen && !canPropose) return null

  return (
    <Panel title="قرارات الحماية">
      <Alert
        tone="info"
        title="الخطر الخارجي معلومة، وليس أمراً تنفيذياً"
        description="لا يتخذ النظام أي إجراء تلقائي. يقترح المدير المسؤول إجراءً، ويعتمده أو يرفضه المدير العام."
      />

      {hasOpen && (
        <ul className={styles.proposalList} data-testid="open-proposals">
          {alert.openProposals.map((proposal) => {
            const Icon = TYPE_ICON[proposal.decisionType]
            return (
              <li key={proposal.id} className={styles.proposalCard}>
                <div className={styles.proposalHead}>
                  <span className={styles.proposalType}>
                    <Icon size={16} strokeWidth={1.9} aria-hidden />
                    {SAFETY_DECISION_TYPE_LABELS[proposal.decisionType]}
                  </span>
                  <Badge tone={SAFETY_PROPOSAL_STATUS_TONE[proposal.status]}>
                    {SAFETY_PROPOSAL_STATUS_LABELS[proposal.status]}
                  </Badge>
                </div>

                <dl className={styles.proposalFacts}>
                  <div>
                    <dt>اقتراح المدير المسؤول</dt>
                    <dd>{SAFETY_ACTION_LABELS[proposal.proposedAction]}</dd>
                  </div>
                  <div>
                    <dt>مبرر القرار</dt>
                    <dd>{proposal.proposalNotes}</dd>
                  </div>
                  {windowLabel(proposal) && (
                    <div>
                      <dt>سريان القرار</dt>
                      <dd>{windowLabel(proposal)}</dd>
                    </div>
                  )}
                  {proposal.workerScope && (
                    <div>
                      <dt>الفئات المشمولة</dt>
                      <dd>{proposal.workerScope}</dd>
                    </div>
                  )}
                  <div>
                    <dt>مقدّم الاقتراح</dt>
                    <dd>
                      {proposal.proposedBy.fullName} — {formatDateTime(proposal.proposedAt)}
                    </dd>
                  </div>
                </dl>

                {proposal.canReview ? (
                  <div className={styles.actionBar}>
                    <Button
                      size="sm"
                      disabled={busy}
                      onClick={() => setRuling({ proposal, verdict: 'approve' })}
                    >
                      {APPROVE_LABEL[proposal.decisionType]}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => setRuling({ proposal, verdict: 'reject' })}
                    >
                      رفض
                    </Button>
                  </div>
                ) : (
                  <p className={styles.notes}>بانتظار موافقة المدير العام.</p>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {!hasOpen && canPropose && (
        <StateCard
          tone="neutral"
          title="لا توجد اقتراحات قيد المراجعة"
          description="يمكنك اقتراح إجراء حماية ليعتمده المدير العام."
        />
      )}

      {canPropose && (
        <div className={styles.actionBar}>
          {alert.availableProposalTypes.map((type) => (
            <Button key={type} size="sm" disabled={busy} onClick={() => setProposing(type)}>
              اقتراح {SAFETY_DECISION_TYPE_LABELS[type]}
            </Button>
          ))}
        </div>
      )}

      <Modal
        open={proposing !== null}
        onClose={() => setProposing(null)}
        title={proposing ? `اقتراح ${SAFETY_DECISION_TYPE_LABELS[proposing]}` : ''}
        footer={
          <>
            <Button variant="ghost" onClick={() => setProposing(null)}>
              إلغاء
            </Button>
            <Button
              loading={propose.isPending}
              disabled={!action || !notes.trim()}
              onClick={() => propose.mutate()}
            >
              إرسال للمدير العام
            </Button>
          </>
        }
      >
        <p className={styles.notes}>
          يُرسل هذا الاقتراح للمراجعة فقط. لا يُنفَّذ ولا يُرسل أي إشعار قبل اعتماد المدير العام.
        </p>
        <Field label="الإجراء المقترح" required>
          {(props) => (
            <select
              {...props}
              value={action}
              onChange={(event) => setAction(event.target.value as SafetyAction)}
            >
              <option value="">اختر إجراءً</option>
              {SAFETY_ACTIONS.map((value) => (
                <option key={value} value={value}>
                  {SAFETY_ACTION_LABELS[value]}
                </option>
              ))}
            </select>
          )}
        </Field>
        <div className={styles.windowRow}>
          <Field label="بداية السريان (اختياري)">
            {(props) => (
              <input
                {...props}
                type="datetime-local"
                value={effectiveFrom}
                onChange={(event) => setEffectiveFrom(event.target.value)}
              />
            )}
          </Field>
          <Field label="نهاية السريان (اختياري)">
            {(props) => (
              <input
                {...props}
                type="datetime-local"
                value={effectiveUntil}
                onChange={(event) => setEffectiveUntil(event.target.value)}
              />
            )}
          </Field>
        </div>
        {proposing === 'worker_protection' && (
          <Field label="الفئات المشمولة (اختياري)" hint="مثال: أطقم العمل في الهواء الطلق">
            {(props) => (
              <input
                {...props}
                value={workerScope}
                onChange={(event) => setWorkerScope(event.target.value)}
              />
            )}
          </Field>
        )}
        <Field label="مبرر الاقتراح" required hint="يظهر للمدير العام عند المراجعة">
          {(props) => (
            <textarea
              {...props}
              rows={4}
              maxLength={SAFETY_NOTES_MAX_LENGTH}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          )}
        </Field>
      </Modal>

      <Modal
        open={ruling !== null}
        onClose={() => setRuling(null)}
        title={
          ruling?.verdict === 'approve'
            ? APPROVE_LABEL[ruling.proposal.decisionType]
            : 'رفض الاقتراح'
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setRuling(null)}>
              إلغاء
            </Button>
            <Button
              loading={decide.isPending}
              disabled={ruling?.verdict === 'reject' && !reason.trim()}
              onClick={() => decide.mutate()}
            >
              {ruling?.verdict === 'approve'
                ? APPROVE_LABEL[ruling.proposal.decisionType]
                : 'رفض'}
            </Button>
          </>
        }
      >
        {ruling?.verdict === 'approve' ? (
          <>
            <Alert
              tone="warning"
              title="أثر الموافقة"
              description={APPROVAL_CONSEQUENCE[ruling.proposal.decisionType]}
            />
            <Field label="ملاحظات الاعتماد (اختياري)">
              {(props) => (
                <textarea
                  {...props}
                  rows={3}
                  maxLength={SAFETY_NOTES_MAX_LENGTH}
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                />
              )}
            </Field>
          </>
        ) : (
          <>
            <p className={styles.notes}>
              لن يتم إرسال أي إشعار للعاملين، ولن يُنفَّذ أي إجراء.
            </p>
            <Field label="سبب الرفض" required>
              {(props) => (
                <textarea
                  {...props}
                  rows={3}
                  maxLength={SAFETY_NOTES_MAX_LENGTH}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
              )}
            </Field>
          </>
        )}
      </Modal>
    </Panel>
  )
}
