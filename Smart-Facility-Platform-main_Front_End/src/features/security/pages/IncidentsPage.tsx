import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { MapPin } from 'lucide-react'
import type { AlertType, Incident, IncidentStatus, Severity } from '@/types'
import {
  ALERT_TYPE_LABELS,
  INCIDENT_STATUS_LABELS,
  INCIDENT_STATUS_TONE,
  SEVERITY_LABELS,
  SEVERITY_TONE,
} from '@/types'
import { formatDateTime, formatNumber, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { createIncident, listIncidents } from '@/api/security'
import { listFacilities } from '@/api/operations'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import {
  ErrorState,
  ProgressBar,
  SkeletonLines,
  StateCard,
} from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section } from '@/components/ui/Display/Display'
import { STATUS_COLORS } from '@/components/charts/chartTheme'
import styles from './Alerts.module.css'

type StatusFilter = IncidentStatus | 'all' | 'open'

const FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'الكل' },
  { value: 'open', label: 'مفتوحة' },
  { value: 'new', label: 'جديد' },
  { value: 'investigating', label: 'قيد التحقيق' },
  { value: 'action_required', label: 'يتطلب إجراء' },
  { value: 'resolved', label: 'تمت المعالجة' },
  { value: 'closed', label: 'مغلق' },
]

const schema = z.object({
  facilityId: z.string().min(1, 'اختر المنشأة'),
  type: z.string().min(1, 'اختر نوع الحادث'),
  description: z.string().trim().min(15, 'اكتب وصفاً لا يقل عن 15 حرفاً'),
  location: z.string().trim().min(3, 'أدخل موقع الحادث'),
  severity: z.string().min(1, 'اختر درجة الخطورة'),
})

type IncidentFormValues = z.infer<typeof schema>

export function IncidentsPage() {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [addOpen, setAddOpen] = useState(false)

  const incidentsQuery = useQuery({ queryKey: qk.incidents.list, queryFn: listIncidents })
  const facilitiesQuery = useQuery({ queryKey: qk.facilities.list, queryFn: listFacilities })

  const facilityName = useCallback(
    (id: string) => facilitiesQuery.data?.find((f) => f.id === id)?.name ?? '—',
    [facilitiesQuery.data],
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<Incident, StatusFilter>(
    incidentsQuery.data,
    {
      searchText: useCallback((i: Incident) => `${i.reference} ${i.description} ${i.location}`, []),
      matchesFilter: useCallback(
        (i: Incident, v: StatusFilter) => (v === 'open' ? i.status !== 'closed' : i.status === v),
        [],
      ),
      allValue: 'all',
    },
  )

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<IncidentFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      facilityId: '',
      type: 'intrusion',
      description: '',
      location: '',
      severity: 'medium',
    },
  })

  const create = useMutation({
    mutationFn: (values: IncidentFormValues) =>
      createIncident({
        facilityId: values.facilityId,
        alertId: null,
        type: values.type as AlertType,
        description: values.description,
        location: values.location,
        severity: values.severity as Severity,
        assigneeId: user.id,
      }),
    onSuccess: (incident) => {
      queryClient.invalidateQueries({ queryKey: qk.incidents.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.security })
      showToast({ tone: 'success', title: 'تم إنشاء الحادث', description: incident.reference })
      setAddOpen(false)
      reset()
      navigate(`/security/incidents/${incident.id}`)
    },
  })

  const incidents = incidentsQuery.data ?? []
  const counts = FILTERS.map((option) => ({
    ...option,
    count:
      option.value === 'all'
        ? incidents.length
        : option.value === 'open'
          ? incidents.filter((i) => i.status !== 'closed').length
          : incidents.filter((i) => i.status === option.value).length,
  }))

  if (incidentsQuery.isError) return <ErrorState error={incidentsQuery.error} />

  return (
    <>
      <PageHeader
        title="إدارة الحوادث"
        description="دورة الحادث: جديد ← قيد التحقيق ← يتطلب إجراء ← تمت المعالجة ← مغلق. لا يُغلق الحادث إلا بعد استكمال جميع الإجراءات وكتابة التقرير النهائي."
        actions={<Button onClick={() => setAddOpen(true)}>+ حادث جديد</Button>}
      />

      <Section>
        <KpiGrid cols={4}>
          <KpiCard
            label="إجمالي الحوادث"
            value={formatNumber(incidents.length)}
            icon="incidents"
            tone="primary"
            loading={incidentsQuery.isPending}
          />
          <KpiCard
            label="حوادث مفتوحة"
            value={formatNumber(incidents.filter((i) => i.status !== 'closed').length)}
            icon="response"
            tone={incidents.some((i) => i.status !== 'closed') ? 'warning' : 'success'}
            loading={incidentsQuery.isPending}
          />
          <KpiCard
            label="تتطلب إجراءً"
            value={formatNumber(incidents.filter((i) => i.status === 'action_required').length)}
            icon="emergency"
            tone="critical"
            loading={incidentsQuery.isPending}
          />
          <KpiCard
            label="مغلقة"
            value={formatNumber(incidents.filter((i) => i.status === 'closed').length)}
            icon="quality"
            tone="success"
            loading={incidentsQuery.isPending}
          />
        </KpiGrid>
      </Section>

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput value={query} onChange={setQuery} placeholder="ابحث برقم الحادث أو الوصف…" />
          <FilterBar options={counts} value={filter} onChange={setFilter} label="تصفية الحوادث" />
        </div>
      </Toolbar>

      {incidentsQuery.isPending ? (
        <SkeletonLines count={6} />
      ) : filtered.length === 0 ? (
        <StateCard title="لا توجد حوادث مطابقة" description="جرّب تعديل البحث أو عوامل التصفية." />
      ) : (
        <div className={styles.grid}>
          {filtered.map((incident) => {
            const doneActions = incident.actions.filter((action) => action.done).length
            const actionProgress =
              incident.actions.length === 0
                ? 0
                : Math.round((doneActions / incident.actions.length) * 100)

            return (
              <Link
                key={incident.id}
                to={`/security/incidents/${incident.id}`}
                className={styles.card}
              >
                <span
                  className={styles.severityBar}
                  style={{ background: STATUS_COLORS[SEVERITY_TONE[incident.severity]] }}
                />

                <div className={styles.cardBody}>
                  <div className={styles.cardHead}>
                    <h3 className={styles.cardTitle}>{ALERT_TYPE_LABELS[incident.type]}</h3>
                    <Badge tone={INCIDENT_STATUS_TONE[incident.status]}>
                      {INCIDENT_STATUS_LABELS[incident.status]}
                    </Badge>
                  </div>

                  <p className={styles.cardLocation}>
                    <MapPin size={13} strokeWidth={2} />
                    {incident.location}
                  </p>

                  <p
                    style={{
                      fontSize: 12,
                      color: 'var(--text-muted)',
                      lineHeight: 1.8,
                      marginTop: 8,
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      lineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                    }}
                  >
                    {incident.description}
                  </p>

                  {incident.actions.length > 0 && (
                    <div style={{ marginTop: 14 }}>
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          fontSize: 11,
                          color: 'var(--text-muted)',
                          marginBottom: 5,
                        }}
                      >
                        <span>الإجراءات المنجزة</span>
                        <span>
                          {formatNumber(doneActions)} / {formatNumber(incident.actions.length)}
                        </span>
                      </div>
                      <ProgressBar value={actionProgress} size="sm" label="الإجراءات المنجزة" />
                    </div>
                  )}

                  <div className={styles.cardFoot}>
                    <span className="mono" style={{ fontSize: 11 }}>
                      {incident.reference}
                    </span>
                    <Badge tone={SEVERITY_TONE[incident.severity]}>
                      {SEVERITY_LABELS[incident.severity]}
                    </Badge>
                  </div>

                  <div className={styles.cardMeta}>
                    <span title={formatDateTime(incident.createdAt)}>
                      {formatRelative(incident.createdAt)}
                    </span>
                    <span>{facilityName(incident.facilityId)}</span>
                  </div>
                </div>
              </Link>
            )
          })}
        </div>
      )}

      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="تسجيل حادث جديد"
        subtitle="للحوادث التي لم ترد عبر نظام المراقبة — مثل البلاغات المباشرة من الموقع."
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setAddOpen(false)}>
              إلغاء
            </Button>
            <Button loading={create.isPending} onClick={handleSubmit((v) => create.mutate(v))}>
              إنشاء الحادث
            </Button>
          </>
        }
      >
        <form onSubmit={handleSubmit((v) => create.mutate(v))} noValidate>
          <FieldRow>
            <Field label="المنشأة" error={errors.facilityId?.message} required>
              {(props) => (
                <select {...props} {...register('facilityId')}>
                  <option value="">اختر المنشأة…</option>
                  {facilitiesQuery.data?.map((facility) => (
                    <option key={facility.id} value={facility.id}>
                      {facility.name}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field label="نوع الحادث" error={errors.type?.message} required>
              {(props) => (
                <select {...props} {...register('type')}>
                  {Object.entries(ALERT_TYPE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </FieldRow>

          <FieldRow>
            <Field label="موقع الحادث" error={errors.location?.message} required>
              {(props) => (
                <input {...props} {...register('location')} placeholder="المبنى — الطابق/المنطقة" />
              )}
            </Field>
            <Field label="درجة الخطورة" error={errors.severity?.message} required>
              {(props) => (
                <select {...props} {...register('severity')}>
                  {Object.entries(SEVERITY_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </FieldRow>

          <Field label="وصف الحادث" error={errors.description?.message} required>
            {(props) => (
              <textarea
                {...props}
                {...register('description')}
                rows={4}
                placeholder="ما الذي حدث، متى، ومن أبلغ عنه…"
              />
            )}
          </Field>
        </form>
      </Modal>
    </>
  )
}
