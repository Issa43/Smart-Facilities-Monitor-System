import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Eye, EyeOff, KeyRound } from 'lucide-react'
import { ROLE_LABELS } from '@/types'
import { DEMO_ACCOUNTS } from '@/api/auth'
import { useAuth } from '@/context/AuthContext'
import { ROLE_ROUTES } from '@/routes/routeConfig'
import { Button } from '@/components/ui/Button/Button'
import { Field } from '@/components/ui/Field/Field'
import { Alert } from '@/components/ui/Feedback/Feedback'
import { AuthLayout } from '../AuthLayout'
import styles from '../Auth.module.css'

const schema = z.object({
  username: z.string().trim().min(1, 'أدخل اسم المستخدم أو البريد الإلكتروني'),
  password: z.string().min(1, 'أدخل كلمة المرور'),
})

type LoginValues = z.infer<typeof schema>

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [serverError, setServerError] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState(false)

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(schema),
    defaultValues: { username: '', password: '' },
  })

  // Already signed in — bounce straight to the dashboard.
  if (user) return <Navigate to={ROLE_ROUTES[user.role].homePath} replace />

  async function onSubmit(values: LoginValues) {
    setServerError(null)
    try {
      const signedIn = await login(values.username, values.password)
      const intended = (location.state as { from?: string } | null)?.from
      navigate(intended ?? ROLE_ROUTES[signedIn.role].homePath, { replace: true })
    } catch (error) {
      setServerError(error instanceof Error ? error.message : 'تعذّر تسجيل الدخول')
    }
  }

  return (
    <AuthLayout>
      <h1 className={styles.formTitle}>تسجيل الدخول</h1>
      <p className={styles.formSub}>
        أدخل بيانات حسابك للوصول إلى لوحة التحكم الخاصة بدورك الوظيفي.
      </p>

      {serverError && (
        <Alert
          tone="critical"
          className={styles.formAlert}
          title="فشل تسجيل الدخول"
          description={serverError}
          onDismiss={() => setServerError(null)}
        />
      )}

      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <Field label="اسم المستخدم أو البريد الإلكتروني" error={errors.username?.message} required>
          {(props) => (
            <input
              {...props}
              {...register('username')}
              type="text"
              autoComplete="username"
              placeholder="admin"
            />
          )}
        </Field>

        <Field label="كلمة المرور" error={errors.password?.message} required>
          {(props) => (
            <div style={{ position: 'relative' }}>
              <input
                {...props}
                {...register('password')}
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                placeholder="••••••••"
                style={{ paddingInlineStart: 44 }}
              />
              <button
                type="button"
                onClick={() => setShowPassword((current) => !current)}
                aria-label={showPassword ? 'إخفاء كلمة المرور' : 'إظهار كلمة المرور'}
                style={{
                  position: 'absolute',
                  insetInlineStart: 12,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--text-faint)',
                  display: 'flex',
                }}
              >
                {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>
          )}
        </Field>

        <div className={styles.formRow}>
          <label className={styles.remember}>
            <input type="checkbox" defaultChecked />
            تذكّرني على هذا الجهاز
          </label>
          <Link to="/forgot-password" className={styles.link}>
            نسيت كلمة المرور؟
          </Link>
        </div>

        <Button type="submit" size="lg" block loading={isSubmitting}>
          تسجيل الدخول
        </Button>
      </form>

      <div className={styles.demoCard}>
        <div className={styles.demoTitle}>
          <KeyRound size={13} strokeWidth={2.2} />
          حسابات تجريبية — اضغط على أي حساب لتعبئة البيانات
        </div>
        <div className={styles.demoGrid}>
          {DEMO_ACCOUNTS.map((account) => (
            <button
              key={account.username}
              type="button"
              className={styles.demoRow}
              onClick={() => {
                setValue('username', account.username, { shouldValidate: true })
                setValue('password', account.password, { shouldValidate: true })
              }}
            >
              <span className={styles.demoRole}>{ROLE_LABELS[account.role]}</span>
              <span className={styles.demoCreds}>
                {account.username} / {account.password}
              </span>
            </button>
          ))}
        </div>
      </div>
    </AuthLayout>
  )
}
