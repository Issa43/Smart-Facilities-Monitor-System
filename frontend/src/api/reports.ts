import type { GeneratedReport, ReportKind } from '@/types'
import { REPORT_KIND_LABELS } from '@/types'
import {
  apiRequest,
  downloadProtectedFile,
  fetchAllPages,
  saveDownloadedFile,
  unsupported,
} from './client'

interface ReportRequestDto {
  id: string
  type: string
  module:
    | 'projects'
    | 'construction'
    | 'materials'
    | 'assets'
    | 'maintenance'
    | 'faults'
    | 'operational_performance'
    | 'security'
    | 'users'
    | 'alerts'
    | 'response'
  parameters: Record<string, unknown>
  format: 'pdf' | 'excel'
  status: GeneratedReport['status']
  failure_details: string | null
  download_available: boolean
  file_size: number | null
  created_by_id: string
  created_at: string
}

const kinds = new Set<ReportKind>([
  'projects',
  'construction',
  'materials',
  'assets',
  'maintenance',
  'faults',
  'incidents',
  'users',
  'alerts',
  'response',
  'operational_performance',
])

function reportKind(value: string): ReportKind {
  return kinds.has(value as ReportKind) ? (value as ReportKind) : 'construction'
}

function fromDto(dto: ReportRequestDto): GeneratedReport {
  const kind = reportKind(dto.type)
  return {
    id: dto.id,
    kind,
    title: REPORT_KIND_LABELS[kind],
    format: dto.format,
    periodLabel:
      typeof dto.parameters.period_label === 'string' ? dto.parameters.period_label : 'غير محدد',
    generatedById: dto.created_by_id,
    generatedAt: dto.created_at,
    sizeKb: dto.file_size === null ? null : Math.ceil(dto.file_size / 1024),
    status: dto.status,
    failureDetails: dto.failure_details,
    downloadAvailable: dto.download_available,
  }
}

function moduleFor(kind: ReportKind): ReportRequestDto['module'] {
  if (kind === 'projects') return 'projects'
  if (kind === 'users') return 'users'
  if (kind === 'materials') return 'materials'
  if (kind === 'assets') return 'assets'
  if (kind === 'maintenance') return 'maintenance'
  if (kind === 'faults') return 'faults'
  if (kind === 'operational_performance') return 'operational_performance'
  if (kind === 'alerts') return 'alerts'
  if (kind === 'response') return 'response'
  if (kind === 'incidents') return 'security'
  return 'construction'
}

export async function listGeneratedReports(): Promise<GeneratedReport[]> {
  const reports = await fetchAllPages<ReportRequestDto>('/reports/requests/')
  return reports.map(fromDto)
}

export async function generateReport(input: {
  kind: ReportKind
  format: GeneratedReport['format']
  periodLabel: string
  generatedById: string
  projectId?: string
  facilityId?: string
  dateFrom?: string
  dateTo?: string
}): Promise<GeneratedReport> {
  const dto = await apiRequest<ReportRequestDto>('/reports/requests/', {
    method: 'POST',
    body: {
      type: input.kind,
      module: moduleFor(input.kind),
      format: input.format,
      parameters: {
        period_label: input.periodLabel,
        ...(input.projectId ? { project_id: input.projectId } : {}),
        ...(input.facilityId ? { facility_id: input.facilityId } : {}),
        ...(input.dateFrom ? { date_from: input.dateFrom } : {}),
        ...(input.dateTo ? { date_to: input.dateTo } : {}),
      },
    },
  })
  return fromDto(dto)
}

export async function downloadGeneratedReport(report: GeneratedReport): Promise<void> {
  if (!report.downloadAvailable) {
    unsupported(report.failureDetails ?? 'ملف التقرير غير جاهز للتنزيل بعد.')
  }
  const extension = report.format === 'excel' ? 'xlsx' : 'pdf'
  const file = await downloadProtectedFile(
    `/reports/requests/${report.id}/download/`,
    `${report.kind}-${report.id}.${extension}`,
  )
  saveDownloadedFile(file)
}

export async function retryGeneratedReport(id: string): Promise<GeneratedReport> {
  return fromDto(
    await apiRequest<ReportRequestDto>(`/reports/requests/${id}/retry/`, {
      method: 'POST',
    }),
  )
}

export async function resetDemoData(): Promise<void> {
  unsupported('إعادة تعيين بيانات تجريبية معطلة لأن وضع الإنتاج يستخدم قاعدة البيانات الحقيقية.')
}
