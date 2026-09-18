import { Link } from 'react-router-dom'
import { ROLES, ROLE_DESCRIPTIONS, ROLE_LABELS } from '@/types'
import { useCurrentUser } from '@/context/AuthContext'
import { ROLE_ROUTES } from '@/routes/routeConfig'
import { PageHeader } from '@/components/layout/PageHeader'
import { Icon } from '@/components/icons'
import { Badge } from '@/components/ui/Badge/Badge'
import { Panel } from '@/components/ui/Panel/Panel'
import { Section, SplitGrid } from '@/components/ui/Display/Display'
import shared from '@/features/shared/Dashboard.module.css'
import styles from './Help.module.css'

const FAQ = [
  {
    question: 'كيف يبدأ مشروع جديد دورته في المنصة؟',
    answer:
      'ينشئ المدير العام المشروع ويسنده إلى مدير إنشاءات. يظهر المشروع فوراً في لوحة تحكم المدير المسؤول، الذي يضيف مراحل التنفيذ ويبدأ متابعتها وتحديث نسب الإنجاز.',
  },
  {
    question: 'متى يتحوّل المشروع من الإنشاء إلى التشغيل؟',
    answer:
      'يتحقق النظام من ثلاثة شروط قبل السماح بذلك: اكتمال جميع المراحل، عدم وجود مرحلة مرفوضة، وعدم وجود طلبات مواد مفتوحة. عند تحقق الشروط يتحوّل المشروع إلى منشأة تشغيلية تظهر لدى مدير التشغيل.',
  },
  {
    question: 'كيف يعمل تنبيه انخفاض المخزون؟',
    answer:
      'لكل مادة حد أدنى للمخزون. عند انخفاض الكمية المتبقية عن هذا الحد، يُنشئ النظام إشعاراً تلقائياً لمدير الإنشاءات والمدير العام، ويظهر في مركز الإشعارات وفي درج الإشعارات أعلى الشاشة.',
  },
  {
    question: 'ما الفرق بين التنبيه والحادث؟',
    answer:
      'التنبيه يصل تلقائياً من نظام المراقبة الخارجي ويحتاج مراجعة فقط. الحادث سجل رسمي يُنشأ عندما يستدعي التنبيه إجراءً فعلياً — ويُوثَّق فيه الإجراءات والأدلة والتقرير النهائي حتى الإغلاق.',
  },
  {
    question: 'لماذا لا أستطيع حذف بعض المستخدمين؟',
    answer:
      'المستخدم المرتبط بسجلات تشغيلية (مشاريع، أوامر صيانة، أو حوادث) لا يمكن حذفه للحفاظ على سلامة البيانات التاريخية. يمكن إيقاف حسابه بدلاً من ذلك، فيُمنع من الدخول مع بقاء سجلاته سليمة.',
  },
  {
    question: 'كيف تُحتسب درجة صحة الأصل؟',
    answer:
      'تبدأ من 100 وتنخفض مع كل عطل يُسجَّل عليه — بمقدار أكبر للأعطال الحرجة — وترتفع عند إغلاق أمر صيانة أو إصلاح عطل. لذلك تعكس الدرجة سجل الأصل الفعلي لا تقديراً ثابتاً.',
  },
]

export function HelpPage() {
  const user = useCurrentUser()
  const config = ROLE_ROUTES[user.role]

  return (
    <>
      <PageHeader
        title="مركز المساعدة"
        description="شرح مبسّط لكيفية عمل المنصة، الأدوار الأربعة، ومسار العمل من الإنشاء حتى التشغيل."
      />

      <Section>
        <Panel title="دورة حياة المنشأة" subtitle="المسار الكامل الذي تديره المنصة">
          <ol className={styles.flow}>
            {[
              {
                step: 1,
                title: 'إنشاء المشروع',
                body: 'المدير العام ينشئ المشروع ويسنده لمدير إنشاءات.',
                icon: 'projects' as const,
              },
              {
                step: 2,
                title: 'التنفيذ',
                body: 'مدير الإنشاءات يضيف المراحل، يتابع الإنجاز، ويدير المواد والجودة.',
                icon: 'stages' as const,
              },
              {
                step: 3,
                title: 'التسليم',
                body: 'بعد اكتمال جميع المراحل واعتمادها، يتحوّل المشروع إلى منشأة تشغيلية.',
                icon: 'quality' as const,
              },
              {
                step: 4,
                title: 'التشغيل',
                body: 'مدير التشغيل يدير الأصول وأوامر الصيانة ويتابع الأعطال.',
                icon: 'maintenance' as const,
              },
              {
                step: 5,
                title: 'الأمن والحوادث',
                body: 'مسؤول الأمن يتابع التنبيهات ويوثّق الحوادث حتى إغلاقها.',
                icon: 'incidents' as const,
              },
            ].map((item) => (
              <li key={item.step} className={styles.flowStep}>
                <span className={styles.flowIcon}>
                  <Icon name={item.icon} size={20} />
                </span>
                <span className={styles.flowNumber}>{item.step}</span>
                <span className={styles.flowTitle}>{item.title}</span>
                <span className={styles.flowBody}>{item.body}</span>
              </li>
            ))}
          </ol>
        </Panel>
      </Section>

      <Section>
        <SplitGrid>
          <Panel title="الأدوار الأربعة">
            <div className={styles.roles}>
              {ROLES.map((role) => (
                <div key={role} className={styles.role}>
                  <div className={styles.roleHead}>
                    <span className={styles.roleName}>{ROLE_LABELS[role]}</span>
                    {role === user.role && <Badge tone="info">دورك الحالي</Badge>}
                  </div>
                  <p className={styles.roleBody}>{ROLE_DESCRIPTIONS[role]}</p>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="صفحاتك" subtitle="جميع الشاشات المتاحة لدورك الوظيفي">
            {config.nav.map((group) => (
              <div key={group.title} className={styles.navGroup}>
                <div className={styles.navTitle}>{group.title}</div>
                {group.items.map((item) => (
                  <Link key={item.path} to={item.path} className={styles.navLink}>
                    <Icon name={item.icon} size={16} />
                    {item.label}
                  </Link>
                ))}
              </div>
            ))}
          </Panel>
        </SplitGrid>
      </Section>

      <Section>
        <Panel title="أسئلة شائعة">
          <div className={styles.faq}>
            {FAQ.map((item) => (
              <details key={item.question} className={styles.faqItem}>
                <summary className={styles.faqQuestion}>{item.question}</summary>
                <p className={styles.faqAnswer}>{item.answer}</p>
              </details>
            ))}
          </div>
        </Panel>
      </Section>

      <Section>
        <Panel title="الدعم الفني">
          <p className={shared.hint}>
            هذه نسخة تجريبية من المنصة تعمل ببيانات محلية بدون خادم. لأي استفسار حول آلية العمل،
            راجع الأسئلة الشائعة أعلاه أو ملف <span className="mono">README.md</span> المرفق مع
            المشروع.
          </p>
        </Panel>
      </Section>
    </>
  )
}
