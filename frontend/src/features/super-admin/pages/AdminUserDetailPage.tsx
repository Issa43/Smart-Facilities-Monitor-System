import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Archive, KeyRound, Pencil } from 'lucide-react'
import type { Role, User } from '@/types'
import {
  ACCOUNT_STATUS_LABELS,
  ACCOUNT_STATUS_TONE,
  ROLES,
  ROLE_DESCRIPTIONS,
  ROLE_LABELS,
} from '@/types'
import { formatDate, formatDateTime, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import {
  deleteUser,
  getUser,
  listAuditLogs,
  resetUserPassword,
  setUserStatus,
  updateUser,
} from '@/api/users'
import { useToast } from '@/context/ToastContext'
import { useCurrentUser } from '@/context/AuthContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { Modal } from '@/components/ui/Modal/Modal'
import { Panel } from '@/components/ui/Panel/Panel'
import { Switch } from '@/components/ui/Controls/Controls'
import { Field, FieldRow } from '@/components/ui/Field/Field'
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

const editUserSchema = z.object({
  fullName: z.string().trim().min(3, 'أدخل الاسم الكامل'),
  phone: z.string().trim().max(30, 'رقم الجوال طويل جداً'),
  role: z.enum(['super_admin', 'construction_manager', 'operations_manager', 'security_officer']),
  status: z.enum(['active', 'inactive', 'suspended']),
})

type EditUserFormValues = z.infer<typeof editUserSchema>

export function AdminUserDetailPage() {
  const { userId = '' } = useParams<{ userId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const currentUser = useCurrentUser()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [profileImage, setProfileImage] = useState<File | null>(null)

  const {
    register,
    handleSubmit,
    reset: resetEdit,
    formState: { errors: editErrors },
  } = useForm<EditUserFormValues>({
    resolver: zodResolver(editUserSchema),
    defaultValues: {
      fullName: '',
      phone: '',
      role: 'construction_manager',
      status: 'active',
    },
  })

  const userQuery = useQuery({
    queryKey: qk.users.detail(userId),
    queryFn: () => getUser(userId),
  })
  const auditQuery = useQuery({ queryKey: qk.auditLogs.all, queryFn: listAuditLogs })

  const user = userQuery.data
  const isSelf = user?.id === currentUser.id
  const userActivity = (auditQuery.data ?? []).filter((entry) => entry.actorId === userId)

  const openEdit = () => {
    if (!user) return
    resetEdit({
      fullName: user.fullName,
      phone: user.phone,
      role: user.role,
      status: user.status,
    })
    setProfileImage(null)
    setEditOpen(true)
  }

  const edit = useMutation({
    mutationFn: (values: EditUserFormValues) =>
      updateUser(userId, {
        fullName: values.fullName,
        phone: values.phone,
        role: values.role as Role,
        status: values.status as User['status'],
        profileImage,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(qk.users.detail(userId), updated)
      queryClient.invalidateQueries({ queryKey: qk.users.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.admin })
      setEditOpen(false)
      setProfileImage(null)
      showToast({
        tone: 'success',
        title: 'تم تحديث بيانات المستخدم',
        description: `${updated.fullName} — ${ROLE_LABELS[updated.role]}`,
      })
    },
    onError: (error) =>
      showToast({
        tone: 'critical',
        title: 'تعذّر تحديث بيانات المستخدم',
        description: error instanceof Error ? error.message : undefined,
      }),
  })

  const toggleStatus = useMutation({
    mutationFn: (active: boolean) => setUserStatus(userId, active ? 'active' : 'suspended'),
    onSuccess: (updated) => {
      queryClient.setQueryData(qk.users.detail(userId), updated)
      queryClient.invalidateQueries({ queryKey: qk.users.all })
      showToast({
        tone: updated.status === 'active' ? 'success' : 'warning',
        title: updated.status === 'active' ? 'تم تفعيل الحساب' : 'تم إيقاف الحساب',
        description: updated.fullName,
      })
    },
    onError: (error) =>
      showToast({
        tone: 'critical',
        title: 'تعذّر تغيير حالة الحساب',
        description: error instanceof Error ? error.message : undefined,
      }),
  })

  const resetPassword = useMutation({
    mutationFn: () => resetUserPassword(userId),
    onSuccess: () =>
      showToast({
        tone: 'success',
        title: 'تم إرسال رابط إعادة التعيين',
        description: 'سيصل المستخدم رابط لتعيين كلمة مرور جديدة على بريده.',
      }),
    onError: (error) =>
      showToast({
        tone: 'critical',
        title: 'الميزة غير متاحة',
        description: error instanceof Error ? error.message : undefined,
      }),
  })

  const remove = useMutation({
    mutationFn: () => deleteUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.users.all })
      showToast({ tone: 'success', title: 'تمت أرشفة الحساب' })
      navigate('/admin/users')
    },
    onError: (error) => {
      setConfirmDelete(false)
      showToast({
        tone: 'critical',
        title: 'تعذّرت أرشفة الحساب',
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
          <>
            <Button variant="ghost" onClick={openEdit}>
              <Pencil size={15} strokeWidth={2} />
              تعديل المستخدم
            </Button>
            <Button
              variant="ghost"
              loading={resetPassword.isPending}
              onClick={() => resetPassword.mutate()}
            >
              <KeyRound size={15} strokeWidth={2} />
              إعادة تعيين كلمة المرور
            </Button>
          </>
        }
      />

      <Section>
        <div className={styles.hero}>
          <Avatar initials={user.initials} imageUrl={user.profileImageUrl} size={92} />
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
                  value:
                    user.hasOperationalRecords === null
                      ? 'غير متاح من واجهة المستخدمين'
                      : user.hasOperationalRecords
                        ? 'نعم'
                        : 'لا',
                },
              ]}
            />
          </div>
        </div>
      </Section>

      <SplitGrid>
        <Panel title="سجل نشاط المستخدم" subtitle="العمليات التي نفّذها داخل النظام">
          {auditQuery.isError ? (
            <Alert tone="warning" title="سجل التدقيق مؤجل" description={auditQuery.error.message} />
          ) : auditQuery.isPending ? (
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
                  disabled={toggleStatus.isPending || isSelf}
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

          <Panel title="أرشفة الحساب">
            <p className={shared.hint} style={{ marginBottom: 14 }}>
              تؤرشف هذه العملية الحساب وتمنع تسجيل الدخول مع الاحتفاظ بالمستخدم وجميع السجلات
              التشغيلية والتاريخية المرتبطة به.
            </p>
            <Button variant="critical" disabled={isSelf} onClick={() => setConfirmDelete(true)}>
              <Archive size={15} strokeWidth={2} />
              أرشفة الحساب
            </Button>
          </Panel>
        </div>
      </SplitGrid>

      <Modal
        open={editOpen}
        onClose={() => setEditOpen(false)}
        title="تعديل بيانات المستخدم"
        subtitle={user.fullName}
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setEditOpen(false)}>
              إلغاء
            </Button>
            <Button
              loading={edit.isPending}
              onClick={handleSubmit((values) => edit.mutate(values))}
            >
              حفظ التغييرات
            </Button>
          </>
        }
      >
        <form onSubmit={handleSubmit((values) => edit.mutate(values))} noValidate>
          <FieldRow>
            <Field label="الاسم الكامل" error={editErrors.fullName?.message} required>
              {(props) => <input {...props} {...register('fullName')} />}
            </Field>
            <Field label="رقم الجوال" error={editErrors.phone?.message}>
              {(props) => <input {...props} {...register('phone')} type="tel" dir="ltr" />}
            </Field>
          </FieldRow>

          <FieldRow>
            <Field label="الدور الوظيفي" error={editErrors.role?.message} required>
              {(props) =>
                isSelf ? (
                  <>
                    <input {...props} value={ROLE_LABELS[user.role]} disabled />
                    <input type="hidden" {...register('role')} />
                  </>
                ) : (
                  <select {...props} {...register('role')}>
                    {ROLES.map((role) => (
                      <option key={role} value={role}>
                        {ROLE_LABELS[role]}
                      </option>
                    ))}
                  </select>
                )
              }
            </Field>
            <Field label="حالة الحساب" error={editErrors.status?.message} required>
              {(props) =>
                isSelf ? (
                  <>
                    <input {...props} value={ACCOUNT_STATUS_LABELS[user.status]} disabled />
                    <input type="hidden" {...register('status')} />
                  </>
                ) : (
                  <select {...props} {...register('status')}>
                    <option value="active">{ACCOUNT_STATUS_LABELS.active}</option>
                    <option value="suspended">{ACCOUNT_STATUS_LABELS.suspended}</option>
                    <option value="inactive">{ACCOUNT_STATUS_LABELS.inactive}</option>
                  </select>
                )
              }
            </Field>
          </FieldRow>

          <Field label="الصورة الشخصية" hint="اترك الحقل فارغاً للاحتفاظ بالصورة الحالية.">
            {(props) => (
              <input
                {...props}
                type="file"
                accept="image/*"
                onChange={(event) => setProfileImage(event.target.files?.[0] ?? null)}
              />
            )}
          </Field>
        </form>
      </Modal>

      <Modal
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="تأكيد أرشفة الحساب"
        subtitle={user.fullName}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
              إلغاء
            </Button>
            <Button variant="critical" loading={remove.isPending} onClick={() => remove.mutate()}>
              نعم، أرشف الحساب
            </Button>
          </>
        }
      >
        <p style={{ fontSize: 13, lineHeight: 1.9, color: 'var(--text-muted)' }}>
          ستتغير حالة الحساب إلى «مؤرشف» ولن يتمكن المستخدم من تسجيل الدخول. سيبقى سجل المستخدم
          وبياناته التاريخية محفوظين، ويمكن للمسؤول إعادة تفعيله لاحقاً.
        </p>
      </Modal>
    </>
  )
}
