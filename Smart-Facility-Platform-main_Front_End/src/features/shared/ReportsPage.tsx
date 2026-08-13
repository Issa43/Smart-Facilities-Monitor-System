import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileSpreadsheet, FileText } from 'lucide-react'
import type { ReportKind } from '@/types'
import { REPORT_KIND_LABELS } from '@/types'
import { formatDateTime, formatFileSize, formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { generateReport, listGeneratedReports } from '@/api/reports'
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
  'آخر 30 يوماً',
  'آخر 90 يوماً',
  'الربع الحالي',
  'السنة الحالية',
  'الوضع الحالي',
] as const

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
  const [period, setPeriod] = useState<string>(PERIODS[0])
  const [pending, setPending] = useState<string | null>(null)

  const reportsQuery = useQuery({ queryKey: qk.reports.generated, queryFn: listGeneratedReports })
  const usersQuery = useQuery({ queryKey: qk.users.all, queryFn: listUsers })

  const generate = useMutation({
    mutationFn: (input: { kind: ReportKind; format: 'pdf' | 'excel' }) =>
      generateReport({ ...input, periodLabel: period, generatedById: user.id }),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: qk.reports.all })
      showToast({
        tone: 'success',
        title: 'تم إصدار التقرير',
        description: `${report.title} — ${report.format === 'pdf' ? 'PDF' : 'Excel'} · ${formatFileSize(report.sizeKb)}`,
      })
    },
    onSettled: () => setPending(null),
  })

  function run(kind: ReportKind, format: 'pdf' | 'excel') {
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
          <label className={styles.periodPicker}>
            <span className={styles.periodLabel}>الفترة</span>
            <select value={period} onChange={(event) => setPeriod(event.target.value)}>
              {PERIODS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
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
              key: 'size',
              header: 'الحجم',
              numeric: true,
              sortValue: (report) => report.sizeKb,
              render: (report) => formatFileSize(report.sizeKb),
            },
            { key: 'by', header: 'أصدره', render: (report) => userName(report.generatedById) },
            {
              key: 'at',
              header: 'وقت الإصدار',
              sortValue: (report) => report.generatedAt,
              render: (report) => formatDateTime(report.generatedAt),
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
