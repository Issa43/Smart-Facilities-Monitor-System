import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RotateCcw } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button/Button'
import { Panel } from '@/components/ui/Panel/Panel'
import { Modal } from '@/components/ui/Modal/Modal'
import { Switch } from '@/components/ui/Controls/Controls'
import { Alert } from '@/components/ui/Feedback/Feedback'
import { DescriptionList, Section } from '@/components/ui/Display/Display'
import { ErrorState } from '@/components/ui/Feedback/Feedback'
import { listSystemSettings, updateSystemSetting, type SystemSetting } from '@/api/settings'
import { useToast } from '@/context/ToastContext'
import styles from './Settings.module.css'

interface ToggleSetting {
  key: string
  label: string
  description: string
  defaultValue: boolean
}

const SECTIONS: { id: string; title: string; settings: ToggleSetting[] }[] = [
  {
    id: 'notifications',
    title: 'الإشعارات والتنبيهات',
    settings: [
      {
        key: 'notify.lowStock',
        label: 'تنبيه انخفاض المخزون',
        description: 'إشعار تلقائي عند انخفاض كمية أي مادة عن الحد الأدنى المحدد لها.',
        defaultValue: true,
      },
      {
        key: 'notify.overdueWorkOrders',
        label: 'تنبيه أوامر الصيانة المتأخرة',
        description: 'إشعار يومي بأوامر الصيانة التي تجاوزت تاريخ التنفيذ المجدول.',
        defaultValue: true,
      },
      {
        key: 'notify.criticalAlerts',
        label: 'التنبيهات الأمنية الحرجة',
        description: 'إشعار فوري للمدير العام عند وصول أي تنبيه أمني بمستوى خطورة حرج.',
        defaultValue: true,
      },
      {
        key: 'notify.stageReview',
        label: 'إشعار المراحل الجاهزة للمراجعة',
        description: 'تنبيه مدير الإنشاءات عند وصول أي مرحلة إلى نسبة إنجاز 100%.',
        defaultValue: true,
      },
    ],
  },
  {
    id: 'security',
    title: 'الأمان',
    settings: [
      {
        key: 'security.sessionTimeout',
        label: 'إنهاء الجلسة تلقائياً',
        description: 'إنهاء جلسة المستخدم بعد 30 دقيقة من عدم النشاط.',
        defaultValue: true,
      },
      {
        key: 'security.auditLog',
        label: 'تسجيل جميع العمليات',
        description: 'توثيق كل عملية إنشاء أو تعديل أو حذف في سجل التدقيق.',
        defaultValue: true,
      },
      {
        key: 'security.passwordPolicy',
        label: 'سياسة كلمات المرور القوية',
        description: 'إلزام المستخدمين بكلمة مرور لا تقل عن 8 أحرف تحتوي على حروف وأرقام.',
        defaultValue: true,
      },
    ],
  },
  {
    id: 'workflow',
    title: 'سير العمل',
    settings: [
      {
        key: 'workflow.requireApproval',
        label: 'إلزام اعتماد المراحل',
        description: 'منع اعتبار أي مرحلة مكتملة قبل مراجعتها واعتمادها من مدير الإنشاءات.',
        defaultValue: true,
      },
      {
        key: 'workflow.blockCompletion',
        label: 'التحقق قبل إنهاء المشروع',
        description:
          'منع تحويل المشروع إلى مرحلة التشغيل قبل اكتمال جميع المراحل وإغلاق طلبات المواد المفتوحة.',
        defaultValue: true,
      },
      {
        key: 'workflow.autoIncident',
        label: 'إنشاء حادث تلقائياً',
        description: 'إنشاء حادث تلقائياً عند وصول تنبيه أمني بمستوى خطورة حرج.',
        defaultValue: false,
      },
    ],
  },
]

export function AdminSettingsPage() {
  const [confirmReset, setConfirmReset] = useState(false)
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const settingsQuery = useQuery({ queryKey: ['system-settings'], queryFn: listSystemSettings })
  const values = new Map(settingsQuery.data?.map((setting) => [setting.key, setting]))
  const update = useMutation({
    mutationFn: ({ setting, value }: { setting: SystemSetting; value: boolean }) =>
      updateSystemSetting(setting, value),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system-settings'] })
      showToast({ tone: 'success', title: 'تم حفظ الإعداد' })
    },
    onError: (error) =>
      showToast({
        tone: 'critical',
        title: 'تعذّر حفظ الإعداد',
        description: error instanceof Error ? error.message : undefined,
      }),
  })

  if (settingsQuery.isError) return <ErrorState error={settingsQuery.error} />

  return (
    <>
      <PageHeader
        title="إعدادات النظام"
        description="ضبط سلوك التنبيهات، سياسات الأمان، وقواعد سير العمل عبر المنصة."
      />

      {SECTIONS.map((section) => (
        <Section key={section.id}>
          <Panel title={section.title}>
            {section.settings.map((setting) => (
              <div key={setting.key} className={styles.row}>
                <div className={styles.rowText}>
                  <div className={styles.rowLabel}>{setting.label}</div>
                  <div className={styles.rowDesc}>{setting.description}</div>
                </div>
                <Switch
                  checked={Boolean(values.get(setting.key)?.value ?? setting.defaultValue)}
                  label={setting.label}
                  disabled={!values.has(setting.key) || update.isPending}
                  onChange={(value) => {
                    const record = values.get(setting.key)
                    if (record) update.mutate({ setting: record, value })
                  }}
                />
              </div>
            ))}
          </Panel>
        </Section>
      ))}

      <Section>
        <Panel title="معلومات النظام">
          <DescriptionList
            items={[
              { label: 'اسم المنصة', value: 'نُظم — إدارة دورة حياة المنشآت' },
              { label: 'الإصدار', value: <span className="mono">1.0.0</span> },
              { label: 'واجهة المستخدم', value: 'React 19 · TypeScript · Vite' },
              { label: 'اللغة والاتجاه', value: 'العربية — من اليمين إلى اليسار' },
              { label: 'مصدر البيانات', value: 'SFLMS Backend API — JWT' },
            ]}
          />
        </Panel>
      </Section>

      <Section>
        <Panel
          title="إدارة بيانات النظام"
          subtitle="عمليات الإدارة الشاملة تتطلب عقداً صريحاً من الخادم"
          actions={
            <Button variant="critical" disabled>
              <RotateCcw size={15} strokeWidth={2} />
              إعادة تعيين البيانات
            </Button>
          }
        >
          <Alert
            tone="info"
            title="غير مدعوم من الخلفية الحالية"
            description="تستخدم هذه النسخة قاعدة البيانات الحقيقية. لا توجد نقطة API لإعادة تعيين بيانات النظام، لذلك بقيت الواجهة معطلة ولا تنفّذ نجاحاً وهمياً. إعدادات التبديل أعلاه معروضة أيضاً للمرجعية فقط حتى يوفّر الخادم عقد إعدادات."
          />
        </Panel>
      </Section>

      <Modal
        open={confirmReset}
        onClose={() => setConfirmReset(false)}
        title="تأكيد إعادة تعيين البيانات"
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmReset(false)}>
              إلغاء
            </Button>
            <Button variant="critical" disabled>
              غير مدعوم
            </Button>
          </>
        }
      >
        <p style={{ fontSize: 13, lineHeight: 1.9, color: 'var(--text-muted)' }}>
          سيتم حذف كل ما أنشأته أو عدّلته خلال هذه الجلسة، وستعود البيانات إلى حالتها الأصلية. لا
          يمكن التراجع عن هذا الإجراء.
        </p>
      </Modal>
    </>
  )
}
