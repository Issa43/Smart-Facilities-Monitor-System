import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { KeyRound, LogOut } from 'lucide-react'
import { ROLE_DESCRIPTIONS, ROLE_LABELS } from '@/types'
import { formatDate, formatDateTime, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { requestPasswordReset, updateCurrentUser } from '@/api/auth'
import { listMyAuditLogs } from '@/api/users'
import { useAuth, useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Panel } from '@/components/ui/Panel/Panel'
import { Alert, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import {
  Avatar,
  DescriptionList,
  Section,
  SplitGrid,
  Timeline,
} from '@/components/ui/Display/Display'
import shared from '@/features/shared/Dashboard.module.css'
import styles from '@/features/shared/ProjectDetail.module.css'
import { selectProfileActivities } from './profileActivity'

const schema = z.object({
  fullName: z.string().trim().min(3, 'أدخل الاسم الكامل'),
  email: z.string().trim().min(1, 'أدخل البريد الإلكتروني').email('صيغة البريد غير صحيحة'),
  phone: z
    .string()
    .trim()
    .regex(/^05\d{8}$/, 'رقم الجوال يجب أن يبدأ بـ 05 ويتكون من 10 أرقام'),
})

type ProfileValues = z.infer<typeof schema>

export function ProfilePage() {
  const user = useCurrentUser()
  const { logout, refreshUser } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [profileImage, setProfileImage] = useState<File | null>(null)

  const auditQuery = useQuery({ queryKey: qk.auditLogs.all, queryFn: listMyAuditLogs })
  const myActivity = selectProfileActivities(auditQuery.data ?? [], user.id)

  const {
    register,
    handleSubmit,
    formState: { errors, isDirty },
  } = useForm<ProfileValues>({
    resolver: zodResolver(schema),
    values: { fullName: user.fullName, email: user.email, phone: user.phone },
  })

  const save = useMutation({
    mutationFn: (values: ProfileValues) =>
      updateCurrentUser({
        fullName: values.fullName,
        phone: values.phone,
        profileImage: profileImage ?? undefined,
      }),
    onSuccess: async () => {
      setProfileImage(null)
      await refreshUser()
      queryClient.invalidateQueries({ queryKey: qk.users.all })
      showToast({
        tone: 'success',
        title: 'تم حفظ التعديلات',
        description: 'تم تحديث الملف الشخصي من الخادم.',
      })
    },
  })

  const resetPassword = useMutation({
    mutationFn: () => requestPasswordReset(user.email),
    onSuccess: () =>
      showToast({
        tone: 'success',
        title: 'تم إرسال رابط إعادة التعيين',
        description: 'تحقّق من بريدك الإلكتروني لتعيين كلمة مرور جديدة.',
      }),
    onError: (error) =>
      showToast({
        tone: 'critical',
        title: 'الميزة غير متاحة',
        description: error instanceof Error ? error.message : undefined,
      }),
  })

  return (
    <>
      <PageHeader
        title="الملف الشخصي"
        description="بياناتك الشخصية، دورك الوظيفي، وسجل نشاطك داخل المنصة."
        actions={
          <Button
            variant="critical"
            onClick={() => {
              logout()
              navigate('/login', { replace: true })
            }}
          >
            <LogOut size={15} strokeWidth={2} />
            تسجيل الخروج
          </Button>
        }
      />

      <Section>
        <div className={styles.hero}>
          <Avatar initials={user.initials} imageUrl={user.profileImageUrl} size={92} />
          <div className={styles.heroBody}>
            <div className={styles.heroTop}>
              <Badge tone="info">{ROLE_LABELS[user.role]}</Badge>
              <Badge tone={user.status === 'active' ? 'success' : 'neutral'}>
                {user.status === 'active' ? 'حساب نشط' : 'حساب موقوف'}
              </Badge>
            </div>
            <DescriptionList
              items={[
                { label: 'الاسم الكامل', value: user.fullName },
                { label: 'اسم المستخدم', value: <span className="mono">{user.username}</span> },
                { label: 'البريد الإلكتروني', value: <span className="mono">{user.email}</span> },
                { label: 'رقم الجوال', value: <span className="mono">{user.phone}</span> },
                {
                  label: 'آخر تسجيل دخول',
                  value: user.lastLoginAt ? formatDateTime(user.lastLoginAt) : '—',
                },
                { label: 'تاريخ إنشاء الحساب', value: formatDate(user.createdAt) },
              ]}
            />
          </div>
        </div>
      </Section>

      <SplitGrid>
        <Panel title="تعديل البيانات الشخصية">
          {save.isError && (
            <Alert
              tone="critical"
              title="تعذّر حفظ الملف الشخصي"
              description={save.error instanceof Error ? save.error.message : undefined}
            />
          )}
          <form onSubmit={handleSubmit((values) => save.mutate(values))} noValidate>
            <Field label="الاسم الكامل" error={errors.fullName?.message} required>
              {(props) => <input {...props} {...register('fullName')} />}
            </Field>

            <FieldRow>
              <Field
                label="البريد الإلكتروني"
                error={errors.email?.message}
                hint="تغيير البريد غير متاح في عقد الملف الشخصي الحالي"
                required
              >
                {(props) => (
                  <input {...props} {...register('email')} type="email" dir="ltr" readOnly />
                )}
              </Field>
              <Field label="رقم الجوال" error={errors.phone?.message} required>
                {(props) => <input {...props} {...register('phone')} type="tel" dir="ltr" />}
              </Field>
            </FieldRow>

            <Field
              label="صورة الملف الشخصي"
              hint={profileImage?.name ?? 'PNG أو JPG؛ يتحقق الخادم من محتوى الصورة'}
            >
              {(props) => (
                <input
                  {...props}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={(event) => setProfileImage(event.target.files?.[0] ?? null)}
                />
              )}
            </Field>

            <Button type="submit" loading={save.isPending} disabled={!isDirty && !profileImage}>
              حفظ التعديلات
            </Button>
          </form>
        </Panel>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Panel title="دورك الوظيفي">
            <p className={shared.hint}>{ROLE_DESCRIPTIONS[user.role]}</p>
          </Panel>

          <Panel title="الأمان">
            <p className={shared.hint} style={{ marginBottom: 14 }}>
              لتغيير كلمة المرور، سنرسل رابطاً آمناً إلى بريدك الإلكتروني المسجّل.
            </p>
            <Button
              variant="ghost"
              block
              loading={resetPassword.isPending}
              onClick={() => resetPassword.mutate()}
            >
              <KeyRound size={15} strokeWidth={2} />
              إعادة تعيين كلمة المرور
            </Button>
          </Panel>
        </div>
      </SplitGrid>

      <Section>
        <Panel title="سجل نشاطي" subtitle="آخر العمليات التي نفّذتها داخل النظام">
          {auditQuery.isError ? (
            <Alert tone="warning" title="سجل التدقيق مؤجل" description={auditQuery.error.message} />
          ) : auditQuery.isPending ? (
            <SkeletonLines count={5} />
          ) : myActivity.length === 0 ? (
            <StateCard
              bare
              title="لا يوجد نشاط مسجّل"
              description="ستظهر هنا العمليات التي تنفّذها داخل المنصة."
            />
          ) : (
            <Timeline
              entries={myActivity.slice(0, 10).map((entry) => ({
                id: entry.id,
                tone: 'info',
                title: entry.title,
                body: entry.body,
                meta: `${formatRelative(entry.createdAt)} · ${entry.ip}`,
              }))}
            />
          )}
        </Panel>
      </Section>
    </>
  )
}
