import type { GeneratedReport, ReportKind } from '@/types'
import { REPORT_KIND_LABELS } from '@/types'
import { delay, newId, nowIso } from './client'
import { clone, commit, getDb } from './db'
import { resetDb } from './db'

export async function listGeneratedReports(): Promise<GeneratedReport[]> {
  await delay()
  return clone(
    getDb()
      .generatedReports.slice()
      .sort((a, b) => b.generatedAt.localeCompare(a.generatedAt)),
  )
}

/**
 * Records a report as generated and returns it.
 *
 * The file itself is not produced — that is a backend concern (a PDF/Excel
 * renderer running server-side). The UI treats the returned record as the
 * download target, which is exactly what it would do against a real API.
 */
export async function generateReport(input: {
  kind: ReportKind
  format: GeneratedReport['format']
  periodLabel: string
  generatedById: string
}): Promise<GeneratedReport> {
  await delay(900) // report generation is genuinely slow — the button shows a spinner
  return commit((db) => {
    const report: GeneratedReport = {
      id: newId('rpt'),
      kind: input.kind,
      title: REPORT_KIND_LABELS[input.kind],
      format: input.format,
      periodLabel: input.periodLabel,
      generatedById: input.generatedById,
      generatedAt: nowIso(),
      sizeKb: 400 + Math.floor(Math.random() * 3600),
    }
    db.generatedReports.unshift(report)
    return clone(report)
  })
}

/** Wired to "إعادة تعيين البيانات التجريبية" in Settings. */
export async function resetDemoData(): Promise<void> {
  await delay(400)
  resetDb()
}
