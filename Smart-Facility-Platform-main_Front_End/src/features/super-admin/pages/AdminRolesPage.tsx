import { useState } from 'react'
import { Check } from 'lucide-react'
import type { Role } from '@/types'
import { ROLES, ROLE_DESCRIPTIONS, ROLE_LABELS } from '@/types'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/ui/Panel/Panel'
import { Section } from '@/components/ui/Display/Display'
import { Alert } from '@/components/ui/Feedback/Feedback'
import shared from '@/features/shared/Dashboard.module.css'
import styles from './Roles.module.css'

interface PermissionGroup {
  title: string
  permissions: { key: string; label: string; roles: Role[] }[]
}

/**
 * The permission model straight from the requirements document. Held as a
 * constant rather than fetched: with no backend there is no server-side
 * authorisation to mirror, and pretending otherwise would be misleading.
 * Toggles are local and clearly presented as a draft.
 */
const GROUPS: PermissionGroup[] = [
  {
    title: 'إدارة المشاريع',
    permissions: [
      { key: 'project.create', label: 'إنشاء المشاريع', roles: ['super_admin'] },
      {
        key: 'project.edit',
        label: 'تعديل بيانات المشروع',
        roles: ['super_admin', 'construction_manager'],
      },
      {
        key: 'project.view',
        label: 'عرض المشاريع',
        roles: ['super_admin', 'construction_manager'],
      },
      {
        key: 'project.close',
        label: 'إنهاء المشروع وتحويله للتشغيل',
        roles: ['super_admin', 'construction_manager'],
      },
    ],
  },
  {
    title: 'مراحل التنفيذ',
    permissions: [
      { key: 'stage.create', label: 'إضافة مرحلة', roles: ['construction_manager'] },
      { key: 'stage.edit', label: 'تعديل مرحلة', roles: ['construction_manager'] },
      { key: 'stage.delete', label: 'حذف مرحلة قبل بدء التنفيذ', roles: ['construction_manager'] },
      { key: 'stage.progress', label: 'تحديث نسبة الإنجاز', roles: ['construction_manager'] },
      { key: 'stage.approve', label: 'اعتماد أو رفض المرحلة', roles: ['construction_manager'] },
    ],
  },
  {
    title: 'إدارة المواد',
    permissions: [
      {
        key: 'material.manage',
        label: 'إضافة وتعديل وحذف المواد',
        roles: ['construction_manager'],
      },
      { key: 'material.request', label: 'إنشاء طلب شراء', roles: ['construction_manager'] },
      {
        key: 'material.stock',
        label: 'متابعة المخزون',
        roles: ['super_admin', 'construction_manager'],
      },
    ],
  },
  {
    title: 'الأصول والصيانة',
    permissions: [
      { key: 'asset.manage', label: 'إضافة وتعديل الأصول', roles: ['operations_manager'] },
      { key: 'asset.status', label: 'تحديث حالة الأصل', roles: ['operations_manager'] },
      { key: 'workorder.create', label: 'إنشاء أمر صيانة', roles: ['operations_manager'] },
      { key: 'workorder.close', label: 'إغلاق أمر الصيانة', roles: ['operations_manager'] },
      { key: 'fault.manage', label: 'تسجيل ومتابعة الأعطال', roles: ['operations_manager'] },
    ],
  },
  {
    title: 'الأمن والحوادث',
    permissions: [
      {
        key: 'alert.view',
        label: 'عرض التنبيهات الأمنية',
        roles: ['super_admin', 'security_officer'],
      },
      { key: 'incident.create', label: 'إنشاء حادث', roles: ['security_officer'] },
      {
        key: 'incident.update',
        label: 'تحديث حالة الحادث',
        roles: ['security_officer', 'operations_manager'],
      },
      { key: 'incident.close', label: 'إغلاق الحادث', roles: ['security_officer'] },
      {
        key: 'incident.escalate',
        label: 'تحويل الحادث لمدير التشغيل',
        roles: ['security_officer'],
      },
    ],
  },
  {
    title: 'التقارير والنظام',
    permissions: [
      {
        key: 'report.generate',
        label: 'إصدار التقارير',
        roles: ['super_admin', 'construction_manager', 'operations_manager', 'security_officer'],
      },
      { key: 'report.all', label: 'الاطلاع على جميع التقارير', roles: ['super_admin'] },
      { key: 'user.manage', label: 'إدارة المستخدمين', roles: ['super_admin'] },
      { key: 'role.manage', label: 'إدارة الصلاحيات', roles: ['super_admin'] },
      { key: 'audit.view', label: 'الاطلاع على سجل التدقيق', roles: ['super_admin'] },
      { key: 'settings.manage', label: 'إدارة إعدادات النظام', roles: ['super_admin'] },
    ],
  },
]

/** Flattens the constant into the mutable "key:role" set the matrix toggles. */
function initialGrants(): Set<string> {
  const grants = new Set<string>()
  for (const group of GROUPS) {
    for (const permission of group.permissions) {
      for (const role of permission.roles) grants.add(`${permission.key}:${role}`)
    }
  }
  return grants
}

export function AdminRolesPage() {
  const { showToast } = useToast()
  const [grants, setGrants] = useState<Set<string>>(initialGrants)

  function toggle(permissionKey: string, role: Role, label: string) {
    const cell = `${permissionKey}:${role}`
    setGrants((current) => {
      const next = new Set(current)
      if (next.has(cell)) next.delete(cell)
      else next.add(cell)

      showToast({
        tone: next.has(cell) ? 'success' : 'warning',
        title: next.has(cell) ? 'تم منح الصلاحية' : 'تم سحب الصلاحية',
        description: `${label} — ${ROLE_LABELS[role]}`,
      })
      return next
    })
  }

  return (
    <>
      <PageHeader
        title="الأدوار والصلاحيات"
        description="مصفوفة الصلاحيات الكاملة للأدوار الأربعة. اضغط على أي خانة لمنح الصلاحية أو سحبها."
      />

      <Section>
        <div className={styles.roleCards}>
          {ROLES.map((role) => (
            <div key={role} className={styles.roleCard}>
              <div className={styles.roleName}>{ROLE_LABELS[role]}</div>
              <p className={styles.roleDesc}>{ROLE_DESCRIPTIONS[role]}</p>
              <div className={styles.roleCount}>
                {[...grants].filter((cell) => cell.endsWith(`:${role}`)).length} صلاحية ممنوحة
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section>
        <Alert
          tone="info"
          title="التعديلات هنا تجريبية"
          description="تُطبَّق التغييرات على الواجهة فقط في هذه النسخة. عند ربط النظام بخادم حقيقي، ستُحفظ الصلاحيات في قاعدة البيانات وتُفرض على مستوى الخادم أيضاً."
        />
      </Section>

      {GROUPS.map((group) => (
        <Section key={group.title}>
          <Panel title={group.title} flush>
            <div className={styles.scroll}>
              <table className={styles.matrix}>
                <thead>
                  <tr>
                    <th>الصلاحية</th>
                    {ROLES.map((role) => (
                      <th key={role}>{ROLE_LABELS[role]}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {group.permissions.map((permission) => (
                    <tr key={permission.key}>
                      <td className={styles.permLabel}>{permission.label}</td>
                      {ROLES.map((role) => {
                        const granted = grants.has(`${permission.key}:${role}`)
                        return (
                          <td key={role}>
                            <button
                              type="button"
                              className={granted ? styles.checkOn : styles.checkOff}
                              onClick={() => toggle(permission.key, role, permission.label)}
                              aria-pressed={granted}
                              aria-label={`${permission.label} — ${ROLE_LABELS[role]}`}
                            >
                              {granted && <Check size={12} strokeWidth={3} />}
                            </button>
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </Section>
      ))}

      <p className={shared.hint} style={{ textAlign: 'center' }}>
        إجمالي الصلاحيات المعرّفة: {GROUPS.reduce((sum, g) => sum + g.permissions.length, 0)} صلاحية
        عبر {GROUPS.length} مجموعات.
      </p>
    </>
  )
}
