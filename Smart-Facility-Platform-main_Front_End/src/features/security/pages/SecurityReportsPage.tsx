import { ReportsPage, type ReportCard } from '@/features/shared/ReportsPage'

const CARDS: ReportCard[] = [
  {
    kind: 'incidents',
    icon: 'incidents',
    description: 'الحوادث المسجّلة، درجات خطورتها، الإجراءات المتخذة، والتقارير النهائية.',
  },
  {
    kind: 'alerts',
    icon: 'securityAlert',
    description: 'التنبيهات الواردة من نظام المراقبة، أنواعها، ونتيجة معالجة كل منها.',
  },
  {
    kind: 'response',
    icon: 'response',
    description: 'أزمنة الاستجابة، الإجراءات المنجزة، ومعدلات إغلاق الحوادث خلال الفترة.',
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
