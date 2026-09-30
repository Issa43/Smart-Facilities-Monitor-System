import { ReportsPage, type ReportCard } from '@/features/shared/ReportsPage'

const CARDS: ReportCard[] = [
  {
    kind: 'incidents',
    icon: 'incidents',
    description: 'الحوادث المسجّلة: نوعها ووصفها وموقعها ودرجة خطورتها وحالتها وتاريخ إغلاقها.',
  },
  {
    kind: 'alerts',
    icon: 'securityAlert',
    description: 'التنبيهات الواردة من نظام المراقبة، أنواعها، ونتيجة معالجة كل منها.',
  },
  {
    kind: 'response',
    icon: 'response',
    description: 'إجراءات الاستجابة المتخذة لكل حادث، ومن نفّذها، ووقت تنفيذها وإنجازها.',
  },
]

export function SecurityReportsPage() {
  return (
    <ReportsPage
      title="التقارير الأمنية"
      description="إصدار تقارير الحوادث والتنبيهات والاستجابة بصيغة PDF أو Excel."
      cards={CARDS}
    />
  )
}
