import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowUpRight, Check, X } from 'lucide-react'
import {
  ALERT_STATUS_LABELS,
  ALERT_STATUS_TONE,
  ALERT_TYPE_LABELS,
  SEVERITY_LABELS,
  SEVERITY_TONE,
} from '@/types'
import { formatDateTime, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { createIncident, getAlert, listIncidents, setAlertStatus } from '@/api/security'
import { getFacility } from '@/api/operations'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { Field } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { Panel } from '@/components/ui/Panel/Panel'
import { Alert, ErrorState, SkeletonLines } from '@/components/ui/Feedback/Feedback'
import { DescriptionList, Section, SplitGrid } from '@/components/ui/Display/Display'
import shared from '@/features/shared/Dashboard.module.css'
import styles from '@/features/shared/ProjectDetail.module.css'

/** Gradients stand in for camera stills — no binary assets in the repo. */
const EVIDENCE = [
  'linear-gradient(135deg, #DDF3FF, #B8E4FA)',
  'linear-gradient(135deg, #F3E8FF, #DDF3FF)',
  'linear-gradient(135deg, #FEF6E0, #F3E8FF)',
]

export function AlertDetailPage() {
  const { alertId = '' } = useParams<{ alertId: string }>()
  const user = useCurrentUser()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [escalateOpen, setEscalateOpen] = useState(false)
  const [description, setDescription] = useState('')

  const alertQuery = useQuery({
    queryKey: qk.alerts.detail(alertId),
    queryFn: () => getAlert(alertId),
  })
  const alert = alertQuery.data

  const facilityQuery = useQuery({
    queryKey: qk.facilities.detail(alert?.facilityId ?? ''),
    queryFn: () => getFacility(alert?.facilityId as string),
    enabled: Boolean(alert?.facilityId),
  })
  const incidentsQuery = useQuery({ queryKey: qk.incidents.list, queryFn: listIncidents })

  const linkedIncident = incidentsQuery.data?.find((incident) => incident.id === alert?.incidentId)

  const updateStatus = useMutation({
    mutationFn: (status: 'acknowledged' | 'dismissed') => setAlertStatus(alertId, status),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: qk.alerts.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.security })
      showToast({
        tone: updated.status === 'dismissed' ? 'neutral' : 'success',
        title: `تم تحديث التنبيه إلى «${ALERT_STATUS_LABELS[updated.status]}»`,
      })
    },
  })

  const escalate = useMutation({
    mutationFn: () =>
      createIncident({
        facilityId: alert?.facilityId ?? '',
        alertId,
        type: alert?.type ?? 'motion',
        description,
        location: alert?.location ?? '',
        severity: alert?.severity ?? 'medium',
        assigneeId: user.id,
      }),
    onSuccess: (incident) => {
      queryClient.invalidateQueries({ queryKey: qk.alerts.all })
      queryClient.invalidateQueries({ queryKey: qk.incidents.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.security })
      showToast({
        tone: 'success',
        title: 'تم إنشاء الحادث',
        description: `${incident.reference} — تم ربطه بالتنبيه.`,
      })
      navigate(`/security/incidents/${incident.id}`)
    },
  })

  if (alertQuery.isError) return <ErrorState error={alertQuery.error} />
  if (alertQuery.isPending || !alert) {
    return (
      <Panel>
        <SkeletonLines count={6} />
      </Panel>
    )
  }

  const canAct = alert.status === 'new' || alert.status === 'acknowledged'

  return (
    <>
      <PageHeader
        title={ALERT_TYPE_LABELS[alert.type]}
        description={`${alert.location} — ${alert.source}`}
        crumbs={[{ label: alert.reference }]}
        actions={
          canAct && (
            <>
              <Button variant="ghost" onClick={() => updateStatus.mutate('dismissed')}>
                <X size={15} strokeWidth={2.2} />
                إنذار كاذب
              </Button>
              {alert.status === 'new' && (
                <Button variant="ghost" onClick={() => updateStatus.mutate('acknowledged')}>
                  <Check size={15} strokeWidth={2.2} />
                  تمت المراجعة
                </Button>
              )}
              <Button
                variant="critical"
                onClick={() => {
                  setDescription(
                    `${ALERT_TYPE_LABELS[alert.type]} في ${alert.location}، تم رصده بواسطة ${alert.source}.`,
                  )
                  setEscalateOpen(true)
                }}
              >
                <ArrowUpRight size={15} strokeWidth={2.2} />
                تصعيد إلى حادث
              </Button>
            </>
          )
        }
      />

      {alert.severity === 'critical' && alert.status === 'new' && (
        <Section>
          <Alert
            tone="critical"
            title="تنبيه حرج بانتظار الإجراء"
            description="هذا التنبيه بمستوى خطورة حرج ولم تُتخذ بشأنه أي إجراءات بعد. راجعه فوراً وقرّر ما إذا كان يستدعي فتح حادث."
          />
        </Section>
      )}

      <Section>
        <div className={styles.hero}>
          <div className={styles.heroBody}>
            <div className={styles.heroTop}>
              <Badge tone={SEVERITY_TONE[alert.severity]} live={alert.status === 'new'}>
                خطورة {SEVERITY_LABELS[alert.severity]}
              </Badge>
              <Badge tone={ALERT_STATUS_TONE[alert.status]}>
                {ALERT_STATUS_LABELS[alert.status]}
              </Badge>
            </div>
            <DescriptionList
              items={[
                { label: 'رقم التنبيه', value: <span className="mono">{alert.reference}</span> },
                { label: 'نوع التنبيه', value: ALERT_TYPE_LABELS[alert.type] },
                { label: 'الموقع', value: alert.location },
                { label: 'المنشأة', value: facilityQuery.data?.name ?? '—' },
                { label: 'مصدر التنبيه', value: alert.source },
                { label: 'وقت الرصد', value: formatDateTime(alert.detectedAt) },
              ]}
            />
          </div>
        </div>
      </Section>

      <SplitGrid>
        <Panel title="لقطات نظام المراقبة" subtitle="الصور المرفقة تلقائياً من الكاميرا المصدر">
          <div className={styles.photoGrid}>
            {EVIDENCE.map((gradient, index) => (
              <figure key={index} className={styles.photo}>
                <div className={styles.photoMedia} style={{ background: gradient }} />
                <figcaption className={styles.photoCaption}>
                  لقطة {index + 1} — {alert.source}
                  <span className={styles.photoDate}>{formatRelative(alert.detectedAt)}</span>
                </figcaption>
              </figure>
            ))}
          </div>
        </Panel>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Panel title="الحادث المرتبط">
            {linkedIncident ? (
              <>
                <p className={shared.hint} style={{ marginBottom: 14 }}>
                  تم تصعيد هذا التنبيه إلى حادث مسجّل في النظام.
                </p>
                <Link
                  to={`/security/incidents/${linkedIncident.id}`}
                  className={shared.attentionRow}
                >
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span className={shared.attentionTitle}>{linkedIncident.reference}</span>
                    <span className={shared.attentionMeta}>{linkedIncident.location}</span>
                  </span>
                  <Badge tone={SEVERITY_TONE[linkedIncident.severity]}>
                    {SEVERITY_LABELS[linkedIncident.severity]}
                  </Badge>
                </Link>
              </>
            ) : (
              <p className={shared.hint}>
                لم يتم ربط هذا التنبيه بأي حادث. إذا كان يستدعي إجراءً ميدانياً، صعّده إلى حادث
                لتوثيق الإجراءات ومتابعتها حتى الإغلاق.
              </p>
            )}
          </Panel>

          <Panel title="سجل الإجراءات">
            <div className={shared.metricList}>
              <div className={shared.metricRow}>
                <span className={shared.metricLabel}>وصول التنبيه من نظام المراقبة</span>
                <span className={shared.metricValue}>{formatRelative(alert.detectedAt)}</span>
              </div>
              <div className={shared.metricRow}>
                <span className={shared.metricLabel}>الحالة الحالية</span>
                <Badge tone={ALERT_STATUS_TONE[alert.status]}>
                  {ALERT_STATUS_LABELS[alert.status]}
                </Badge>
              </div>
            </div>
          </Panel>
        </div>
      </SplitGrid>

      <Modal
        open={escalateOpen}
        onClose={() => setEscalateOpen(false)}
        title="تصعيد التنبيه إلى حادث"
        subtitle="سيُنشأ حادث جديد مرتبط بهذا التنبيه، وستتغير حالة التنبيه إلى «تم التصعيد»."
        footer={
          <>
            <Button variant="ghost" onClick={() => setEscalateOpen(false)}>
              إلغاء
            </Button>
            <Button
              variant="critical"
              loading={escalate.isPending}
              disabled={description.trim().length < 10}
              onClick={() => escalate.mutate()}
            >
              إنشاء الحادث
            </Button>
          </>
        }
      >
        <Field label="وصف الحادث" hint="سيظهر هذا الوصف في سجل الحادث — اذكر ما رُصد وأين" required>
          {(props) => (
            <textarea
              {...props}
              rows={4}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          )}
        </Field>

        <DescriptionList
          items={[
            { label: 'النوع', value: ALERT_TYPE_LABELS[alert.type] },
            { label: 'الموقع', value: alert.location },
            { label: 'درجة الخطورة', value: SEVERITY_LABELS[alert.severity] },
            { label: 'المُسند إليه', value: user.fullName },
          ]}
        />
      </Modal>
    </>
  )
}
