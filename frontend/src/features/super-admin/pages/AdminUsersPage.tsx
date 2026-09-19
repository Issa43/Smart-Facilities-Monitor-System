import { useDeferredValue, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import type { AccountStatus, Role, User } from '@/types'
import { ACCOUNT_STATUS_LABELS, ACCOUNT_STATUS_TONE, ROLES, ROLE_LABELS } from '@/types'
import { formatDate, formatNumber, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { createUser, listUsersPage, type UserOrdering } from '@/api/users'
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
import { createUserSchema, type CreateUserFormValues } from '@/features/super-admin/userValidation'

type RoleFilter = Role | 'all'
type StatusFilter = AccountStatus | 'all'

const USER_ORDERINGS: { value: UserOrdering; label: string }[] = [
  { value: '-created_at', label: 'الأحدث إنشاءً' },
  { value: 'created_at', label: 'الأقدم إنشاءً' },
  { value: 'full_name', label: 'الاسم: أ–ي' },
  { value: '-full_name', label: 'الاسم: ي–أ' },
]

export function AdminUsersPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [addOpen, setAddOpen] = useState(false)
  const [page, setPage] = useState(1)
  const [query, setQueryValue] = useState('')
  const [filter, setFilterValue] = useState<RoleFilter>('all')
  const [statusFilter, setStatusFilterValue] = useState<StatusFilter>('all')
  const [ordering, setOrderingValue] = useState<UserOrdering>('-created_at')
  const deferredQuery = useDeferredValue(query)

  const usersQuery = useQuery({
    queryKey: [...qk.users.all, 'page', page, deferredQuery, filter, statusFilter, ordering],
    queryFn: () =>
      listUsersPage({
        page,
        search: deferredQuery,
        role: filter === 'all' ? undefined : filter,
        status: statusFilter === 'all' ? undefined : statusFilter,
        ordering,
      }),
    placeholderData: (previous) => previous,
  })

  const setQuery = (value: string) => {
    setQueryValue(value)
    setPage(1)
  }
  const setFilter = (value: RoleFilter) => {
    setFilterValue(value)
    setPage(1)
  }
  const setStatusFilter = (value: StatusFilter) => {
    setStatusFilterValue(value)
    setPage(1)
  }
  const setOrdering = (value: UserOrdering) => {
    setOrderingValue(value)
    setPage(1)
  }

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreateUserFormValues>({
    resolver: zodResolver(createUserSchema),
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
    mutationFn: (values: CreateUserFormValues) =>
      createUser({
        fullName: values.fullName,
        email: values.email,
        phone: values.phone,
        username: values.username,
        role: values.role as Role,
        status: values.status as User['status'],
        password: values.password,
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

  const roleFilters = [
    { value: 'all' as RoleFilter, label: 'الكل', count: usersQuery.data?.count },
    ...ROLES.map((role) => ({
      value: role as RoleFilter,
      label: ROLE_LABELS[role],
    })),
  ]

  const statusFilters = [
    { value: 'all' as StatusFilter, label: 'كل الحالات' },
    { value: 'active' as StatusFilter, label: ACCOUNT_STATUS_LABELS.active },
    { value: 'suspended' as StatusFilter, label: ACCOUNT_STATUS_LABELS.suspended },
    { value: 'inactive' as StatusFilter, label: ACCOUNT_STATUS_LABELS.inactive },
  ]

  const columns: Column<User>[] = [
    {
      key: 'user',
      header: 'المستخدم',
      render: (user) => (
        <span style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
          <Avatar initials={user.initials} imageUrl={user.profileImageUrl} size={34} />
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
      render: (user) => <Badge tone="info">{ROLE_LABELS[user.role]}</Badge>,
    },
    {
      key: 'email',
      header: 'البريد الإلكتروني',
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
      render: (user) => (
        <Badge tone={ACCOUNT_STATUS_TONE[user.status]}>{ACCOUNT_STATUS_LABELS[user.status]}</Badge>
      ),
    },
    {
      key: 'lastLogin',
      header: 'آخر دخول',
      render: (user) => (user.lastLoginAt ? formatRelative(user.lastLoginAt) : 'لم يسجّل الدخول'),
    },
    {
      key: 'created',
      header: 'تاريخ الإنشاء',
      render: (user) => formatDate(user.createdAt),
    },
  ]

  if (usersQuery.isError) return <ErrorState error={usersQuery.error} />

  return (
    <>
      <PageHeader
        title="المستخدمون"
        description={`${formatNumber(usersQuery.data?.count ?? 0)} حساب موزّع على أربعة أدوار وظيفية. المدير العام وحده يملك صلاحية إنشاء الحسابات وتوزيع الصلاحيات.`}
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
            options={roleFilters}
            value={filter}
            onChange={setFilter}
            label="تصفية المستخدمين حسب الدور"
          />
          <FilterBar
            options={statusFilters}
            value={statusFilter}
            onChange={setStatusFilter}
            label="تصفية المستخدمين حسب حالة الحساب"
          />
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
            <span>الترتيب</span>
            <select
              value={ordering}
              onChange={(event) => setOrdering(event.target.value as UserOrdering)}
              aria-label="ترتيب المستخدمين من الخادم"
            >
              {USER_ORDERINGS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Toolbar>

      <DataTable
        columns={columns}
        rows={usersQuery.data?.items ?? []}
        rowKey={(user) => user.id}
        onRowClick={(user) => navigate(`/admin/users/${user.id}`)}
        loading={usersQuery.isPending}
        pagination={
          usersQuery.data
            ? {
                page: usersQuery.data.page,
                totalPages: usersQuery.data.totalPages,
                totalItems: usersQuery.data.count,
                onPageChange: setPage,
              }
            : undefined
        }
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
              hint="8 أحرف على الأقل، وغير شائعة أو رقمية بالكامل أو مشابهة لبيانات الحساب"
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
                <option value="inactive">مؤرشف</option>
              </select>
            )}
          </Field>
        </form>
      </Modal>
    </>
  )
}
