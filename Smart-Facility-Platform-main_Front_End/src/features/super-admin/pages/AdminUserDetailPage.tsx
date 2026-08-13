import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { KeyRound, Trash2 } from 'lucide-react'
import { ACCOUNT_STATUS_LABELS, ACCOUNT_STATUS_TONE, ROLE_DESCRIPTIONS, ROLE_LABELS } from '@/types'
import { formatDate, formatDateTime, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { deleteUser, getUser, listAuditLogs, resetUserPassword, setUserStatus } from '@/api/users'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { Modal } from '@/components/ui/Modal/Modal'
import { Panel } from '@/components/ui/Panel/Panel'
import { Switch } from '@/components/ui/Controls/Controls'
import { Alert, ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import {
  Avatar,
  DescriptionList,
  Section,
  SplitGrid,
  Timeline,
} from '@/components/ui/Display/Display'
import shared from '@/features/shared/Dashboard.module.css'
import styles from '@/features/shared/ProjectDetail.module.css'

export function AdminUserDetailPage() {
  const { userId = '' } = useParams<{ userId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [confirmDelete, setConfirmDelete] = useState(false)

  const userQuery = useQuery({
    queryKey: qk.users.detail(userId),
    queryFn: () => getUser(userId),
  })
  const auditQuery = useQuery({ queryKey: qk.auditLogs.all, queryFn: listAuditLogs })

  const user = userQuery.data
  const userActivity = (auditQuery.data ?? []).filter((entry) => entry.actorId === userId)

  const toggleStatus = useMutation({
    mutationFn: (active: boolean) => setUserStatus(userId, active ? 'active' : 'suspended'),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: qk.users.all })
      showToast({
        tone: updated.status === 'active' ? 'success' : 'warning',
        title: updated.status === 'active' ? 'تم تفعيل الحساب' : 'تم إيقاف الحساب',
        description: updated.fullName,
      })
    },
  })

  const resetPassword = useMutation({
    mutationFn: () => resetUserPassword(userId),
    onSuccess: () =>
      showToast({
        tone: 'success',
        title: 'تم إرسال رابط إعادة التعيين',
        description: 'سيصل المستخدم رابط لتعيين كلمة مرور جديدة على بريده.',
      }),
  })

  const remove = useMutation({
    mutationFn: () => deleteUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.users.all })
      showToast({ tone: 'success', title: 'تم حذف الحساب' })
      navigate('/admin/users')
    },
    onError: (error) => {
      setConfirmDelete(false)
      showToast({
        tone: 'critical',
        title: 'تعذّر حذف الحساب',
        description: error instanceof Error ? error.message : undefined,
      })
    },
  })

  if (userQuery.isError) return <ErrorState error={userQuery.error} />
  if (userQuery.isPending || !user) {
    return (
      <Panel>
        <SkeletonLines count={7} />
      </Panel>
    )
  }

  return (
    <>
      <PageHeader
        title={user.fullName}
        description={ROLE_DESCRIPTIONS[user.role]}
        crumbs={[{ label: user.fullName }]}
        actions={
          <Button
            variant="ghost"
            loading={resetPassword.isPending}
            onClick={() => resetPassword.mutate()}
          >
            <KeyRound size={15} strokeWidth={2} />
            إعادة تعيين كلمة المرور
          </Button>
        }
      />

      <Section>
        <div className={styles.hero}>
          <Avatar initials={user.initials} size={92} />
          <div className={styles.heroBody}>
            <div className={styles.heroTop}>
              <Badge tone="info">{ROLE_LABELS[user.role]}</Badge>
              <Badge tone={ACCOUNT_STATUS_TONE[user.status]}>
                {ACCOUNT_STATUS_LABELS[user.status]}
              </Badge>
            </div>
            <DescriptionList
              items={[
                { label: 'اسم المستخدم', value: <span className="mono">{user.username}</span> },
                { label: 'البريد الإلكتروني', value: <span className="mono">{user.email}</span> },
                { label: 'رقم الجوال', value: <span className="mono">{user.phone}</span> },
                {
                  label: 'آخر تسجيل دخول',
                  value: user.lastLoginAt
                    ? formatDateTime(user.lastLoginAt)
                    : 'لم يسجّل الدخول بعد',
                },
                { label: 'تاريخ الإنشاء', value: formatDate(user.createdAt) },
                {
                  label: 'سجلات تشغيلية مرتبطة',
                  value: user.hasOperationalRecords ? 'نعم' : 'لا',
                },
              ]}
            />
          </div>
        </div>
      </Section>

      <SplitGrid>
        <Panel title="سجل نشاط المستخدم" subtitle="العمليات التي نفّذها داخل النظام">
          {auditQuery.isPending ? (
            <SkeletonLines count={5} />
          ) : userActivity.length === 0 ? (
            <StateCard
              bare
              title="لا يوجد نشاط مسجّل"
              description="لم ينفّذ هذا المستخدم أي عملية داخل النظام حتى الآن."
            />
          ) : (
            <Timeline
              entries={userActivity.slice(0, 10).map((entry) => ({
                id: entry.id,
                tone: 'info',
                title: entry.action,
                body: `${entry.entity} · ${entry.entityRef}`,
                meta: `${formatRelative(entry.createdAt)} · ${entry.ip}`,
              }))}
            />
          )}
        </Panel>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Panel title="إدارة الحساب">
            <div className={shared.metricList}>
              <div className={shared.metricRow}>
                <div>
                  <div
                    className={shared.metricLabel}
                    style={{ color: 'var(--text)', fontWeight: 700 }}
                  >
                    الحساب مفعّل
                  </div>
                  <div className={shared.hint} style={{ fontSize: 11.5 }}>
                    إيقاف الحساب يمنع تسجيل الدخول دون حذف أي بيانات.
                  </div>
                </div>
                <Switch
                  checked={user.status === 'active'}
                  onChange={(checked) => toggleStatus.mutate(checked)}
                  label="تفعيل أو إيقاف الحساب"
                />
              </div>
            </div>
          </Panel>

          <Panel title="صلاحيات الدور">
            <p className={shared.hint}>{ROLE_DESCRIPTIONS[user.role]}</p>
            <div style={{ marginTop: 14 }}>
              <Button variant="ghost" size="sm" onClick={() => navigate('/admin/roles')}>
                عرض مصفوفة الصلاحيات الكاملة
              </Button>
            </div>
          </Panel>

          <Panel title="منطقة الخطر">
            {user.hasOperationalRecords ? (
              <Alert
                tone="warning"
                title="لا يمكن حذف هذا الحساب"
                description="المستخدم مرتبط بسجلات تشغيلية (مشاريع، أوامر صيانة، أو حوادث). يمكن إيقاف الحساب بدلاً من حذفه للحفاظ على سلامة البيانات التاريخية."
              />
            ) : (
              <>
                <p className={shared.hint} style={{ marginBottom: 14 }}>
                  هذا الحساب غير مرتبط بأي سجلات تشغيلية، ويمكن حذفه نهائياً.
                </p>
                <Button variant="critical" onClick={() => setConfirmDelete(true)}>
                  <Trash2 size={15} strokeWidth={2} />
                  حذف الحساب
                </Button>
              </>
            )}
          </Panel>
        </div>
      </SplitGrid>

      <Modal
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="تأكيد حذف الحساب"
        subtitle={user.fullName}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
              إلغاء
            </Button>
            <Button variant="critical" loading={remove.isPending} onClick={() => remove.mutate()}>
              نعم، احذف الحساب
            </Button>
          </>
        }
      >
        <p style={{ fontSize: 13, lineHeight: 1.9, color: 'var(--text-muted)' }}>
          سيتم حذف الحساب نهائياً ولن يتمكن المستخدم من تسجيل الدخول. لا يمكن التراجع عن هذا
          الإجراء.
        </p>
      </Modal>
    </>
  )
}
