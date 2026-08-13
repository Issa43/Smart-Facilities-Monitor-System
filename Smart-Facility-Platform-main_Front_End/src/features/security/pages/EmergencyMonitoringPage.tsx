import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Siren } from 'lucide-react'
import type { AlertType, Severity } from '@/types'
import {
  ALERT_TYPE_LABELS,
  FACILITY_STATUS_LABELS,
  FACILITY_STATUS_TONE,
  SEVERITY_LABELS,
  SEVERITY_TONE,
} from '@/types'
import { formatNumber, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { createIncident, listAlerts } from '@/api/security'
import { listFacilities } from '@/api/operations'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { Panel } from '@/components/ui/Panel/Panel'
import { ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { Section, SplitGrid } from '@/components/ui/Display/Display'
import { STATUS_COLORS } from '@/components/charts/chartTheme'
import shared from '@/features/shared/Dashboard.module.css'
import styles from './Emergency.module.css'

const EMERGENCY_TYPES: AlertType[] = ['fire', 'smoke', 'emergency', 'intrusion']

export function EmergencyMonitoringPage() {
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [declareOpen, setDeclareOpen] = useState(false)
  const [form, setForm] = useState({
    facilityId: '',
    type: 'emergency' as AlertType,
    location: '',
    description: '',
  })

  const alertsQuery = useQuery({ queryKey: qk.alerts.list, queryFn: listAlerts })
  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })

  const criticalAlerts = (alertsQuery.data ?? []).filter(
    (alert) => alert.severity === 'critical' && alert.status === 'new',
  )
  const emergencyAlerts = (alertsQuery.data ?? []).filter(
    (alert) => EMERGENCY_TYPES.includes(alert.type) && alert.status === 'new',
  )

  const isAllClear = criticalAlerts.length === 0

  const declare = useMutation({
    mutationFn: () =>
      createIncident({
        facilityId: form.facilityId,
        alertId: null,
        type: form.type,
        description: form.description,
        location: form.location,
        severity: 'critical' as Severity,
        assigneeId: user.id,
      }),
    onSuccess: (incident) => {
      queryClient.invalidateQueries({ queryKey: qk.incidents.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.security })
      setDeclareOpen(false)
      showToast({
        tone: 'critical',
        title: 'تم إعلان حالة الطوارئ',
        description: `${incident.reference} — تم إشعار الإدارة.`,
      })
    },
  })

  if (alertsQuery.isError) return <ErrorState error={alertsQuery.error} />

  return (
    <>
      <PageHeader
        title="المراقبة الطارئة"
        description="لوحة الحالة الحرجة — تعرض فقط التنبيهات التي تستدعي استجابة فورية عبر جميع المنشآت."
        actions={
          <Button variant="critical" onClick={() => setDeclareOpen(true)}>
            <Siren size={15} strokeWidth={2.2} />
            إعلان حالة طوارئ
          </Button>
        }
      />

      <Section>
        <div
          className={
            isAllClear ? styles.statusPanel : `${styles.statusPanel} ${styles.statusAlarm}`
          }
        >
          <div className={styles.orbWrap}>
            <span className={styles.orb} />
            <span className={styles.orbRing} />
          </div>
          <div>
            <h2 className={styles.statusTitle}>
              {isAllClear ? 'الوضع مستقر — لا توجد حالات طارئة' : 'حالة تأهب — تنبيهات حرجة نشطة'}
            </h2>
            <p className={styles.statusBody}>
              {isAllClear
                ? `تمت مراجعة جميع التنبيهات الحرجة عبر ${formatNumber(facilitiesQuery.data?.length ?? 0)} منشآت. أنظمة المراقبة تعمل بشكل طبيعي.`
                : `${formatNumber(criticalAlerts.length)} تنبيه حرج بانتظار الإجراء الفوري. راجع القائمة أدناه وابدأ إجراءات الاستجابة.`}
            </p>
          </div>
        </div>
      </Section>

      <Section>
        <SplitGrid>
          <Panel
            title="التنبيهات الحرجة النشطة"
            subtitle="تنبيهات بمستوى خطورة حرج لم تُتخذ بشأنها إجراءات"
          >
            {alertsQuery.isPending ? (
              <SkeletonLines count={4} />
            ) : emergencyAlerts.length === 0 ? (
              <StateCard
                bare
                title="لا توجد تنبيهات طارئة"
                description="جميع أنظمة الإنذار في وضع طبيعي."
              />
            ) : (
              <div className={shared.attentionList}>
                {emergencyAlerts.map((alert) => (
                  <Link
                    key={alert.id}
                    to={`/security/alerts/${alert.id}`}
                    className={shared.attentionRow}
                  >
                    <span
                      className={shared.attentionBar}
                      style={{ background: STATUS_COLORS[SEVERITY_TONE[alert.severity]] }}
                    />
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span className={shared.attentionTitle}>{ALERT_TYPE_LABELS[alert.type]}</span>
                      <span className={shared.attentionMeta}>
                        {alert.location} · {alert.source} · {formatRelative(alert.detectedAt)}
                      </span>
                    </span>
                    <Badge tone={SEVERITY_TONE[alert.severity]} live>
                      {SEVERITY_LABELS[alert.severity]}
                    </Badge>
                  </Link>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="حالة المنشآت" subtitle="الوضع الأمني الحالي لكل منشأة">
            {facilitiesQuery.isPending ? (
              <SkeletonLines count={5} />
            ) : (
              <div className={shared.metricList}>
                {facilitiesQuery.data?.map((facility) => {
                  const facilityAlerts = criticalAlerts.filter(
                    (alert) => alert.facilityId === facility.id,
                  )
                  return (
                    <div key={facility.id} className={shared.metricRow}>
                      <span className={shared.metricLabel}>
                        <span
                          className={styles.facilityDot}
                          style={{
                            background:
                              facilityAlerts.length > 0
                                ? STATUS_COLORS.critical
                                : STATUS_COLORS.success,
                          }}
                        />
                        {facility.name}
                      </span>
                      {facilityAlerts.length > 0 ? (
                        <Badge tone="critical" live>
                          {formatNumber(facilityAlerts.length)} تنبيه حرج
                        </Badge>
                      ) : (
                        <Badge tone={FACILITY_STATUS_TONE[facility.status]}>
                          {FACILITY_STATUS_LABELS[facility.status]}
                        </Badge>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </Panel>
        </SplitGrid>
      </Section>

      <Modal
        open={declareOpen}
        onClose={() => setDeclareOpen(false)}
        title="إعلان حالة طوارئ"
        subtitle="سيُنشأ حادث بدرجة خطورة حرجة، ويُشعَر المدير العام ومسؤولو الأمن فوراً."
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeclareOpen(false)}>
              إلغاء
            </Button>
            <Button
              variant="critical"
              loading={declare.isPending}
              disabled={
                !form.facilityId || form.location.length < 3 || form.description.length < 15
              }
              onClick={() => declare.mutate()}
            >
              <Siren size={15} strokeWidth={2.2} />
              تأكيد إعلان الطوارئ
            </Button>
          </>
        }
      >
        <FieldRow>
          <Field label="المنشأة" required>
            {(props) => (
              <select
                {...props}
                value={form.facilityId}
                onChange={(event) => setForm({ ...form, facilityId: event.target.value })}
              >
                <option value="">اختر المنشأة…</option>
                {facilitiesQuery.data?.map((facility) => (
                  <option key={facility.id} value={facility.id}>
                    {facility.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="نوع الطارئ" required>
            {(props) => (
              <select
                {...props}
                value={form.type}
                onChange={(event) => setForm({ ...form, type: event.target.value as AlertType })}
              >
                {EMERGENCY_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {ALERT_TYPE_LABELS[type]}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </FieldRow>

        <Field label="الموقع الدقيق" hint="3 أحرف على الأقل" required>
          {(props) => (
            <input
              {...props}
              value={form.location}
              onChange={(event) => setForm({ ...form, location: event.target.value })}
              placeholder="المبنى الرئيسي — الطابق الثالث"
            />
          )}
        </Field>

        <Field label="وصف الحالة" hint="15 حرفاً على الأقل" required>
          {(props) => (
            <textarea
              {...props}
              rows={4}
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
              placeholder="ما الذي يحدث، وما الإجراء العاجل المطلوب…"
            />
          )}
        </Field>
      </Modal>
    </>
  )
}
