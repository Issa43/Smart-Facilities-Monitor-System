import { ReportsPage, type ReportCard } from '@/features/shared/ReportsPage'

/** The seven report types the requirements list for the Super Admin. */
const CARDS: ReportCard[] = [
  {
    kind: 'projects',
    icon: 'projects',
    description: 'حالة جميع المشاريع، نسب الإنجاز، المراحل الحالية، والانحراف عن الجدول الزمني.',
  },
  {
    kind: 'construction',
    icon: 'stages',
    description: 'تفصيل مراحل التنفيذ، الأعمال المنجزة، ونتائج فحوصات الجودة لكل مشروع.',
  },
  {
    kind: 'materials',
    icon: 'materials',
    description: 'حركة المواد، الكميات المستخدمة والمتبقية، وطلبات الشراء وحالاتها.',
  },
  {
    kind: 'assets',
    icon: 'assets',
    description: 'جرد الأصول التشغيلية، حالتها، درجات صحتها، وتواريخ آخر صيانة.',
  },
  {
    kind: 'maintenance',
    icon: 'maintenance',
    description: 'أوامر الصيانة الوقائية والتصحيحية، أزمنة الاستجابة، ومعدلات الإنجاز.',
  },
  {
    kind: 'incidents',
    icon: 'incidents',
    description: 'الحوادث الأمنية المسجّلة، مستويات الخطورة، الإجراءات المتخذة، وأزمنة الإغلاق.',
  },
  {
    kind: 'users',
    icon: 'users',
    description: 'حسابات المستخدمين، أدوارهم، حالاتهم، ونشاطهم داخل النظام.',
  },
]

export function AdminReportsPage() {
  return (
    <ReportsPage
      title="مركز التقارير"
      description="إصدار وتصدير التقارير الشاملة لجميع مراحل دورة حياة المنشآت بصيغة PDF أو Excel."
      cards={CARDS}
    />
  )
}
