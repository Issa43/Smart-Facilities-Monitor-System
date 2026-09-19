import { ReportsPage, type ReportCard } from '@/features/shared/ReportsPage'

const CARDS: ReportCard[] = [
  {
    kind: 'construction',
    icon: 'reports',
    description:
      'تقرير مشروع شامل للمراحل والتقدم والتقارير اليومية والمواد والجودة والمستندات والصور.',
  },
]

export function ConstructionReportsPage() {
  return (
    <ReportsPage
      title="تقارير الإنشاءات"
      description="إصدار تقارير المشاريع والتنفيذ والمواد بصيغة PDF أو Excel."
      cards={CARDS}
    />
  )
}
