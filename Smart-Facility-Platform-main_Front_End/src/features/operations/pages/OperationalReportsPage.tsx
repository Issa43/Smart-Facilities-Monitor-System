import { ReportsPage, type ReportCard } from '@/features/shared/ReportsPage'

const CARDS: ReportCard[] = [
  {
    kind: 'maintenance',
    icon: 'maintenance',
    description: 'أوامر الصيانة الوقائية والتصحيحية، حالاتها، ومعدلات الإنجاز خلال الفترة.',
  },
  {
    kind: 'assets',
    icon: 'assets',
    description: 'جرد الأصول، درجات صحتها، تواريخ آخر صيانة، والعمر التشغيلي المتبقي.',
  },
  {
    kind: 'incidents',
    icon: 'faults',
    description: 'سجل الأعطال، مستويات الخطورة، الأسباب الجذرية، وأزمنة الإصلاح.',
  },
  {
    kind: 'operational_performance',
    icon: 'analytics',
    description: 'الجاهزية التشغيلية لكل منشأة، ومقارنة الأداء، ومؤشرات الكفاءة العامة.',
  },
]

export function OperationalReportsPage() {
  return (
    <ReportsPage
      title="التقارير التشغيلية"
      description="إصدار تقارير الصيانة والأصول والأعطال والأداء التشغيلي بصيغة PDF أو Excel."
      cards={CARDS}
    />
  )
}
