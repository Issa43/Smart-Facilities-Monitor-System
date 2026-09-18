import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Eye, EyeOff } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { ROLE_ROUTES } from '@/routes/routeConfig'
import { Button } from '@/components/ui/Button/Button'
import { Field } from '@/components/ui/Field/Field'
import { Alert } from '@/components/ui/Feedback/Feedback'
import { RouteFallback } from '@/routes/RouteFallback'
import { AuthLayout } from '../AuthLayout'
import styles from '../Auth.module.css'

const schema = z.object({
  email: z.string().trim().min(1, 'أدخل البريد الإلكتروني').email('صيغة البريد غير صحيحة'),
  password: z.string().min(1, 'أدخل كلمة المرور'),
})

type LoginValues = z.infer<typeof schema>

export function LoginPage() {
  const { user, login, isInitializing } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [serverError, setServerError] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '' },
  })

  if (isInitializing) return <RouteFallback />

  // Already signed in — bounce straight to the dashboard.
  if (user) return <Navigate to={ROLE_ROUTES[user.role].homePath} replace />

  async function onSubmit(values: LoginValues) {
    setServerError(null)
    try {
      const signedIn = await login(values.email, values.password)
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
        <Field label="البريد الإلكتروني" error={errors.email?.message} required>
          {(props) => (
            <input
              {...props}
              {...register('email')}
              type="email"
              autoComplete="email"
              placeholder="name@example.com"
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
          <span />
          <Link to="/forgot-password" className={styles.link}>
            نسيت كلمة المرور؟
          </Link>
        </div>

        <Button type="submit" size="lg" block loading={isSubmitting}>
          تسجيل الدخول
        </Button>
      </form>
    </AuthLayout>
  )
}
