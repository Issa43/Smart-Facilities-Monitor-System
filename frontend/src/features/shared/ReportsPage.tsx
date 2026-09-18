import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileSpreadsheet, FileText, RotateCcw } from 'lucide-react'
import type { GeneratedReport, ReportKind } from '@/types'
import { REPORT_KIND_LABELS } from '@/types'
import { formatDateTime, formatFileSize, formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import {
  downloadGeneratedReport,
  generateReport,
  listGeneratedReports,
  retryGeneratedReport,
} from '@/api/reports'
import { listProjects } from '@/api/construction'
import { listFacilities } from '@/api/operations'
import { listSecurityFacilities } from '@/api/security'
import { listUsers } from '@/api/users'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { Panel } from '@/components/ui/Panel/Panel'
import { Icon, type IconName } from '@/components/icons'
import { ErrorState, StateCard } from '@/components/ui/Feedback/Feedback'
import { Section } from '@/components/ui/Display/Display'
import styles from './Reports.module.css'

export interface ReportCard {
  kind: ReportKind
  icon: IconName
  description: string
}

interface ReportsPageProps {
  title: string
  description: string
  cards: ReportCard[]
}

const PERIODS = [
  { value: '30d', label: 'آخر 30 يوماً' },
  { value: '90d', label: 'آخر 90 يوماً' },
  { value: 'quarter', label: 'الربع الحالي' },
  { value: 'year', label: 'السنة الحالية' },
  { value: 'current', label: 'الوضع الحالي' },
] as const

function periodParameters(period: string) {
  const today = new Date()
  const dateTo = today.toISOString().slice(0, 10)
  let dateFrom: Date | null = null
  if (period === '30d' || period === '90d') {
    dateFrom = new Date(today)
    dateFrom.setDate(dateFrom.getDate() - (period === '30d' ? 30 : 90))
  } else if (period === 'quarter') {
    dateFrom = new Date(today.getFullYear(), Math.floor(today.getMonth() / 3) * 3, 1)
  } else if (period === 'year') {
    dateFrom = new Date(today.getFullYear(), 0, 1)
  }
  return dateFrom ? { dateFrom: dateFrom.toISOString().slice(0, 10), dateTo } : {}
}

export function reportPollingInterval(reports: GeneratedReport[] | undefined): 3000 | false {
  return reports?.some((report) => report.status === 'queued' || report.status === 'processing')
    ? 3000
    : false
}

/**
 * Shared by all four roles — only the card list differs.
 *
 * "Generating" records the report and returns its metadata. Rendering an actual
 * PDF or Excel file is a server responsibility; the UI treats the returned
 * record as the download target exactly as it would against a real API.
 */
export function ReportsPage({ title, description, cards }: ReportsPageProps) {
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [period, setPeriod] = useState<string>(PERIODS[0].value)
  const [scopeId, setScopeId] = useState('')
  const [pending, setPending] = useState<string | null>(null)

  const reportsQuery = useQuery({
    queryKey: qk.reports.generated,
    queryFn: listGeneratedReports,
    refetchInterval: (query) => reportPollingInterval(query.state.data),
  })
  const usersQuery = useQuery({ queryKey: qk.users.all, queryFn: listUsers })
  const projectsQuery = useQuery({
    queryKey: qk.projects.all,
    queryFn: () => listProjects(user.id),
    enabled: user.role === 'construction_manager',
  })
  const facilitiesQuery = useQuery<Array<{ id: string; name: string }>>({
    queryKey: [...qk.facilities.all, 'report-scope'],
    queryFn: async () => {
      const facilities =
        user.role === 'security_officer' ? await listSecurityFacilities() : await listFacilities()
      return facilities.map(({ id, name }) => ({ id, name }))
    },
    enabled: user.role === 'operations_manager' || user.role === 'security_officer',
  })
  const needsProject = user.role === 'construction_manager'
  const needsFacility = user.role === 'operations_manager' || user.role === 'security_officer'
  const scopeOptions = needsProject ? (projectsQuery.data ?? []) : (facilitiesQuery.data ?? [])

  const generate = useMutation({
    mutationFn: (input: { kind: ReportKind; format: 'pdf' | 'excel' }) =>
      generateReport({
        ...input,
        periodLabel: PERIODS.find((option) => option.value === period)?.label ?? period,
        ...periodParameters(period),
        generatedById: user.id,
        ...(needsProject ? { projectId: scopeId } : {}),
        ...(needsFacility ? { facilityId: scopeId } : {}),
      }),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: qk.reports.all })
      showToast({
        tone: 'success',
        title: 'تم إرسال طلب التقرير',
        description: `${report.title} — ${report.format === 'pdf' ? 'PDF' : 'Excel'} · بانتظار المعالجة`,
      })
    },
    onError: (error) =>
      showToast({
        tone: 'critical',
        title: 'تعذّر إنشاء التقرير',
        description: error instanceof Error ? error.message : undefined,
      }),
    onSettled: () => setPending(null),
  })

  const download = useMutation({
    mutationFn: (report: GeneratedReport) => downloadGeneratedReport(report),
    onError: (error) =>
      showToast({
        tone: 'critical',
        title: 'تعذّر تنزيل التقرير',
        description: error instanceof Error ? error.message : undefined,
      }),
  })

  const retry = useMutation({
    mutationFn: (id: string) => retryGeneratedReport(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.reports.all })
      showToast({ tone: 'success', title: 'تمت إعادة التقرير إلى قائمة المعالجة' })
    },
    onError: (error) =>
      showToast({
        tone: 'critical',
        title: 'تعذرت إعادة محاولة التقرير',
        description: error instanceof Error ? error.message : undefined,
      }),
  })

  function run(kind: ReportKind, format: 'pdf' | 'excel') {
    if ((needsProject || needsFacility) && !scopeId) {
      showToast({
        tone: 'warning',
        title: needsProject ? 'اختر المشروع أولاً' : 'اختر المنشأة أولاً',
      })
      return
    }
    setPending(`${kind}-${format}`)
    generate.mutate({ kind, format })
  }

  if (reportsQuery.isError) return <ErrorState error={reportsQuery.error} />

  const userName = (id: string) =>
    usersQuery.data?.find((candidate) => candidate.id === id)?.fullName ?? '—'

  return (
    <>
      <PageHeader
        title={title}
        description={description}
        actions={
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {(needsProject || needsFacility) && (
              <label className={styles.periodPicker}>
                <span className={styles.periodLabel}>{needsProject ? 'المشروع' : 'المنشأة'}</span>
                <select value={scopeId} onChange={(event) => setScopeId(event.target.value)}>
                  <option value="">اختر...</option>
                  {scopeOptions.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className={styles.periodPicker}>
              <span className={styles.periodLabel}>الفترة</span>
              <select value={period} onChange={(event) => setPeriod(event.target.value)}>
                {PERIODS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        }
      />

      <Section>
        <div className={styles.cards}>
          {cards.map((card) => (
            <article key={card.kind} className={styles.card}>
              <span className={styles.cardIcon}>
                <Icon name={card.icon} size={22} />
              </span>
              <h3 className={styles.cardTitle}>{REPORT_KIND_LABELS[card.kind]}</h3>
              <p className={styles.cardDesc}>{card.description}</p>
              <div className={styles.cardActions}>
                <Button
                  size="sm"
                  variant="ghost"
                  loading={pending === `${card.kind}-pdf`}
                  onClick={() => run(card.kind, 'pdf')}
                >
                  <FileText size={14} strokeWidth={2} />
                  PDF
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  loading={pending === `${card.kind}-excel`}
                  onClick={() => run(card.kind, 'excel')}
                >
                  <FileSpreadsheet size={14} strokeWidth={2} />
                  Excel
                </Button>
              </div>
            </article>
          ))}
        </div>
      </Section>

      <Panel
        title="التقارير المُصدَرة"
        subtitle={`${formatNumber(reportsQuery.data?.length ?? 0)} تقرير في السجل`}
        flush
      >
        <DataTable
          card={false}
          loading={reportsQuery.isPending}
          rows={reportsQuery.data ?? []}
          rowKey={(report) => report.id}
          columns={[
            {
              key: 'title',
              header: 'التقرير',
              sortValue: (report) => report.title,
              render: (report) => (
                <span style={{ display: 'flex', alignItems: 'center', gap: 9, fontWeight: 700 }}>
                  {report.format === 'pdf' ? (
                    <FileText size={15} strokeWidth={2} />
                  ) : (
                    <FileSpreadsheet size={15} strokeWidth={2} />
                  )}
                  {report.title}
                </span>
              ),
            },
            {
              key: 'format',
              header: 'الصيغة',
              render: (report) => (
                <Badge tone={report.format === 'pdf' ? 'critical' : 'success'} plain>
                  {report.format === 'pdf' ? 'PDF' : 'Excel'}
                </Badge>
              ),
            },
            { key: 'period', header: 'الفترة', render: (report) => report.periodLabel },
            {
              key: 'status',
              header: 'الحالة',
              render: (report) => (
                <div>
                  <Badge
                    tone={
                      report.status === 'completed'
                        ? 'success'
                        : report.status === 'failed'
                          ? 'critical'
                          : 'warning'
                    }
                  >
                    {report.status === 'queued'
                      ? 'في قائمة الانتظار'
                      : report.status === 'processing'
                        ? 'قيد المعالجة'
                        : report.status === 'completed'
                          ? 'مكتمل'
                          : 'فشل'}
                  </Badge>
                  {report.status === 'failed' && report.failureDetails && (
                    <div style={{ marginTop: 4, fontSize: 11, color: 'var(--critical-dark)' }}>
                      {report.failureDetails}
                    </div>
                  )}
                </div>
              ),
            },
            {
              key: 'size',
              header: 'الحجم',
              numeric: true,
              sortValue: (report) => report.sizeKb ?? 0,
              render: (report) =>
                report.sizeKb === null ? 'غير متاح من API' : formatFileSize(report.sizeKb),
            },
            { key: 'by', header: 'أصدره', render: (report) => userName(report.generatedById) },
            {
              key: 'at',
              header: 'وقت الإصدار',
              sortValue: (report) => report.generatedAt,
              render: (report) => formatDateTime(report.generatedAt),
            },
            {
              key: 'download',
              header: 'الملف',
              render: (report) =>
                report.status === 'failed' ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={retry.isPending && retry.variables === report.id}
                    onClick={() => retry.mutate(report.id)}
                  >
                    <RotateCcw size={14} strokeWidth={2} />
                    إعادة المحاولة
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={!report.downloadAvailable}
                    loading={download.isPending}
                    onClick={() => download.mutate(report)}
                  >
                    <Download size={14} strokeWidth={2} />
                    تنزيل
                  </Button>
                ),
            },
          ]}
          empty={
            <StateCard
              bare
              title="لم يتم إصدار أي تقارير بعد"
              description="اختر نوع التقرير والصيغة من البطاقات أعلاه لإصدار أول تقرير."
            />
          }
        />
      </Panel>
    </>
  )
}
