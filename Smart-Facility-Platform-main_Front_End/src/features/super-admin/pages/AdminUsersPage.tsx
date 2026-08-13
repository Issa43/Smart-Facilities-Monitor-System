import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import type { Role, User } from '@/types'
import { ACCOUNT_STATUS_LABELS, ACCOUNT_STATUS_TONE, ROLES, ROLE_LABELS } from '@/types'
import { formatDate, formatNumber, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { createUser, listUsers } from '@/api/users'
import { useListFilter } from '@/hooks/useListFilter'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { DataTable, type Column } from '@/components/ui/DataTable/DataTable'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { ErrorState, StateCard } from '@/components/ui/Feedback/Feedback'
import { Avatar } from '@/components/ui/Display/Display'

type RoleFilter = Role | 'all'

const schema = z.object({
  fullName: z.string().trim().min(3, 'أدخل الاسم الكامل'),
  email: z.string().trim().min(1, 'أدخل البريد الإلكتروني').email('صيغة البريد غير صحيحة'),
  phone: z
    .string()
    .trim()
    .regex(/^05\d{8}$/, 'رقم الجوال يجب أن يبدأ بـ 05 ويتكون من 10 أرقام'),
  username: z
    .string()
    .trim()
    .min(3, 'اسم المستخدم يجب ألا يقل عن 3 أحرف')
    .regex(/^[a-zA-Z0-9._-]+$/, 'يُسمح بالحروف اللاتينية والأرقام والنقطة والشرطة فقط'),
  password: z.string().min(8, 'كلمة المرور يجب ألا تقل عن 8 أحرف'),
  role: z.string().min(1, 'اختر الدور الوظيفي'),
  status: z.string().min(1, 'اختر حالة الحساب'),
})

type UserFormValues = z.infer<typeof schema>

export function AdminUsersPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [addOpen, setAddOpen] = useState(false)

  const usersQuery = useQuery({ queryKey: qk.users.all, queryFn: listUsers })

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<User, RoleFilter>(
    usersQuery.data,
    {
      searchText: useCallback(
        (user: User) => `${user.fullName} ${user.email} ${user.username}`,
        [],
      ),
      matchesFilter: useCallback((user: User, value: RoleFilter) => user.role === value, []),
      allValue: 'all',
    },
  )

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<UserFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      fullName: '',
      email: '',
      phone: '',
      username: '',
      password: '',
      role: '',
      status: 'active',
    },
  })

  const create = useMutation({
    mutationFn: (values: UserFormValues) =>
      createUser({
        fullName: values.fullName,
        email: values.email,
        phone: values.phone,
        username: values.username,
        role: values.role as Role,
        status: values.status as User['status'],
      }),
    onSuccess: (user) => {
      queryClient.invalidateQueries({ queryKey: qk.users.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.admin })
      showToast({
        tone: 'success',
        title: 'تم إنشاء الحساب',
        description: `${user.fullName} — ${ROLE_LABELS[user.role]}`,
      })
      setAddOpen(false)
      reset()
    },
    onError: (error) =>
      showToast({
        tone: 'critical',
        title: 'تعذّر إنشاء الحساب',
        description: error instanceof Error ? error.message : undefined,
      }),
  })

  const filters = [
    { value: 'all' as RoleFilter, label: 'الكل', count: usersQuery.data?.length },
    ...ROLES.map((role) => ({
      value: role as RoleFilter,
      label: ROLE_LABELS[role],
      count: usersQuery.data?.filter((user) => user.role === role).length,
    })),
  ]

  const columns: Column<User>[] = [
    {
      key: 'user',
      header: 'المستخدم',
      sortValue: (user) => user.fullName,
      render: (user) => (
        <span style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
          <Avatar initials={user.initials} size={34} />
          <span>
            <span style={{ display: 'block', fontWeight: 700 }}>{user.fullName}</span>
            <span style={{ display: 'block', fontSize: 11.5, color: 'var(--text-muted)' }}>
              <span className="mono">{user.username}</span>
            </span>
          </span>
        </span>
      ),
    },
    {
      key: 'role',
      header: 'الدور الوظيفي',
      sortValue: (user) => ROLE_LABELS[user.role],
      render: (user) => <Badge tone="info">{ROLE_LABELS[user.role]}</Badge>,
    },
    {
      key: 'email',
      header: 'البريد الإلكتروني',
      sortValue: (user) => user.email,
      render: (user) => <span className="mono">{user.email}</span>,
    },
    {
      key: 'phone',
      header: 'رقم الجوال',
      render: (user) => <span className="mono">{user.phone}</span>,
    },
    {
      key: 'status',
      header: 'الحالة',
      sortValue: (user) => user.status,
      render: (user) => (
        <Badge tone={ACCOUNT_STATUS_TONE[user.status]}>{ACCOUNT_STATUS_LABELS[user.status]}</Badge>
      ),
    },
    {
      key: 'lastLogin',
      header: 'آخر دخول',
      sortValue: (user) => user.lastLoginAt ?? '',
      render: (user) => (user.lastLoginAt ? formatRelative(user.lastLoginAt) : 'لم يسجّل الدخول'),
    },
    {
      key: 'created',
      header: 'تاريخ الإنشاء',
      sortValue: (user) => user.createdAt,
      render: (user) => formatDate(user.createdAt),
    },
  ]

  if (usersQuery.isError) return <ErrorState error={usersQuery.error} />

  return (
    <>
      <PageHeader
        title="المستخدمون"
        description={`${formatNumber(usersQuery.data?.length ?? 0)} حساب موزّع على أربعة أدوار وظيفية. المدير العام وحده يملك صلاحية إنشاء الحسابات وتوزيع الصلاحيات.`}
        actions={<Button onClick={() => setAddOpen(true)}>+ مستخدم جديد</Button>}
      />

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder="ابحث بالاسم أو البريد أو اسم المستخدم…"
          />
          <FilterBar
            options={filters}
            value={filter}
            onChange={setFilter}
            label="تصفية المستخدمين حسب الدور"
          />
        </div>
      </Toolbar>

      <DataTable
        columns={columns}
        rows={filtered}
        rowKey={(user) => user.id}
        onRowClick={(user) => navigate(`/admin/users/${user.id}`)}
        loading={usersQuery.isPending}
        empty={
          <StateCard
            bare
            title="لا يوجد مستخدمون مطابقون"
            description="جرّب تعديل كلمة البحث أو اختيار دور آخر."
          />
        }
      />

      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="إضافة مستخدم جديد"
        subtitle="سيتمكن المستخدم من تسجيل الدخول فور إنشاء الحساب حسب صلاحيات دوره."
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setAddOpen(false)}>
              إلغاء
            </Button>
            <Button
              loading={create.isPending}
              onClick={handleSubmit((values) => create.mutate(values))}
            >
              إنشاء الحساب
            </Button>
          </>
        }
      >
        <form onSubmit={handleSubmit((values) => create.mutate(values))} noValidate>
          <FieldRow>
            <Field label="الاسم الكامل" error={errors.fullName?.message} required>
              {(props) => <input {...props} {...register('fullName')} placeholder="محمد العتيبي" />}
            </Field>
            <Field label="الدور الوظيفي" error={errors.role?.message} required>
              {(props) => (
                <select {...props} {...register('role')}>
                  <option value="">اختر الدور…</option>
                  {ROLES.map((role) => (
                    <option key={role} value={role}>
                      {ROLE_LABELS[role]}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </FieldRow>

          <FieldRow>
            <Field label="البريد الإلكتروني" error={errors.email?.message} required>
              {(props) => (
                <input
                  {...props}
                  {...register('email')}
                  type="email"
                  dir="ltr"
                  placeholder="name@nozom.sa"
                />
              )}
            </Field>
            <Field label="رقم الجوال" error={errors.phone?.message} required>
              {(props) => (
                <input
                  {...props}
                  {...register('phone')}
                  type="tel"
                  dir="ltr"
                  placeholder="05xxxxxxxx"
                />
              )}
            </Field>
          </FieldRow>

          <FieldRow>
            <Field label="اسم المستخدم" error={errors.username?.message} required>
              {(props) => (
                <input {...props} {...register('username')} dir="ltr" placeholder="m.otaibi" />
              )}
            </Field>
            <Field
              label="كلمة المرور"
              error={errors.password?.message}
              hint="8 أحرف على الأقل — يمكن للمستخدم تغييرها لاحقاً"
              required
            >
              {(props) => <input {...props} {...register('password')} type="password" />}
            </Field>
          </FieldRow>

          <Field label="حالة الحساب" error={errors.status?.message} required>
            {(props) => (
              <select {...props} {...register('status')}>
                <option value="active">نشط</option>
                <option value="suspended">موقوف</option>
              </select>
            )}
          </Field>
        </form>
      </Modal>
    </>
  )
}
