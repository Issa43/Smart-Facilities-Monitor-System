import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import type { Role } from '@/types'
import { ROLES, ROLE_DESCRIPTIONS, ROLE_LABELS } from '@/types'
import { useToast } from '@/context/ToastContext'
import { listRoles, updateRolePermissions } from '@/api/users'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/ui/Panel/Panel'
import { Section } from '@/components/ui/Display/Display'
import { Alert, ErrorState, SkeletonLines } from '@/components/ui/Feedback/Feedback'
import shared from '@/features/shared/Dashboard.module.css'
import styles from './Roles.module.css'

interface PermissionGroup {
  title: string
  permissions: { key: string; label: string; roles: Role[] }[]
}

/**
 * This is the backend-approved permission catalog used to label and group
 * persisted grants. The role assignments themselves always come from the
 * roles API and are never inferred from these presentation hints.
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

export function AdminRolesPage() {
  const { showToast } = useToast()
  const [grants, setGrants] = useState<Set<string>>(new Set())
  const [savingCell, setSavingCell] = useState<string | null>(null)
  const rolesQuery = useQuery({ queryKey: ['roles', 'permissions'], queryFn: listRoles })

  useEffect(() => {
    if (!rolesQuery.data) return
    setGrants(
      new Set(
        rolesQuery.data.flatMap((role) =>
          role.permissions.map((permission) => `${permission}:${role.name}`),
        ),
      ),
    )
  }, [rolesQuery.data])

  async function toggle(permissionKey: string, role: Role, label: string) {
    if (role === 'super_admin' || savingCell) return
    const cell = `${permissionKey}:${role}`
    const next = new Set(grants)
    if (next.has(cell)) next.delete(cell)
    else next.add(cell)
    const permissions = [...next]
      .filter((candidate) => candidate.endsWith(`:${role}`))
      .map((candidate) => candidate.slice(0, candidate.lastIndexOf(':')))
    try {
      setSavingCell(cell)
      await updateRolePermissions(role, permissions)
      setGrants(next)
      showToast({
        tone: next.has(cell) ? 'success' : 'warning',
        title: next.has(cell) ? 'تم منح الصلاحية' : 'تم سحب الصلاحية',
        description: `${label} — ${ROLE_LABELS[role]}`,
      })
    } catch (error) {
      showToast({
        tone: 'critical',
        title: 'تعذّر حفظ الصلاحية',
        description: error instanceof Error ? error.message : undefined,
      })
    } finally {
      setSavingCell(null)
    }
  }

  const permissionCount = GROUPS.reduce((sum, group) => sum + group.permissions.length, 0)
  const granted = (permissionKey: string, role: Role) =>
    role === 'super_admin' || grants.has(`${permissionKey}:${role}`)

  if (rolesQuery.isPending) {
    return (
      <>
        <PageHeader
          title="الأدوار والصلاحيات"
          description="جارٍ تحميل مصفوفة الصلاحيات المطبّقة من الخادم."
        />
        <Section>
          <Panel>
            <SkeletonLines count={8} />
          </Panel>
        </Section>
      </>
    )
  }

  if (rolesQuery.isError) {
    return (
      <>
        <PageHeader
          title="الأدوار والصلاحيات"
          description="تعذّر تحميل مصفوفة الصلاحيات المطبّقة من الخادم."
        />
        <Section>
          <ErrorState error={rolesQuery.error} />
        </Section>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="الأدوار والصلاحيات"
        description="مصفوفة الصلاحيات المطبّقة من الخادم. يمكن تعديل الأدوار التشغيلية، بينما يبقى المدير العام دور طوارئ محمياً بكامل الصلاحيات."
      />

      <Section>
        <div className={styles.roleCards}>
          {ROLES.map((role) => (
            <div key={role} className={styles.roleCard}>
              <div className={styles.roleName}>{ROLE_LABELS[role]}</div>
              <p className={styles.roleDesc}>{ROLE_DESCRIPTIONS[role]}</p>
              <div className={styles.roleCount}>
                {role === 'super_admin'
                  ? permissionCount
                  : [...grants].filter((cell) => cell.endsWith(`:${role}`)).length}{' '}
                صلاحية ممنوحة
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section>
        <Alert
          tone="info"
          title="صلاحيات مرتبطة بالخادم"
          description="تُحفظ تغييرات الأدوار التشغيلية في قاعدة البيانات وتُطبّق على طلبات API مع نطاقات المشاريع والمنشآت. صلاحيات المدير العام محمية وغير قابلة للتعديل لأنها تتجاوز قائمة المنح المخزنة بوصفها صلاحية طوارئ."
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
                        const isGranted = granted(permission.key, role)
                        const isProtected = role === 'super_admin'
                        return (
                          <td key={role}>
                            <button
                              type="button"
                              className={isGranted ? styles.checkOn : styles.checkOff}
                              onClick={() => toggle(permission.key, role, permission.label)}
                              disabled={isProtected || savingCell !== null}
                              aria-pressed={isGranted}
                              aria-label={`${permission.label} — ${ROLE_LABELS[role]}${
                                isProtected ? ' — صلاحية محمية' : ''
                              }`}
                            >
                              {isGranted && <Check size={12} strokeWidth={3} />}
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
        إجمالي الصلاحيات المعرّفة: {permissionCount} صلاحية عبر {GROUPS.length} مجموعات.
      </p>
    </>
  )
}
