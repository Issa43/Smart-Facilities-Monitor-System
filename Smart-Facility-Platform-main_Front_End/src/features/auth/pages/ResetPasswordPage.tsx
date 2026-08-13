import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { LinkIcon } from 'lucide-react'
import { resetPassword } from '@/api/auth'
import { Button } from '@/components/ui/Button/Button'
import { Field } from '@/components/ui/Field/Field'
import { Alert } from '@/components/ui/Feedback/Feedback'
import { AuthLayout } from '../AuthLayout'
import styles from '../Auth.module.css'

const schema = z
  .object({
    password: z
      .string()
      .min(8, 'كلمة المرور يجب ألا تقل عن 8 أحرف')
      .regex(/[A-Za-z]/, 'يجب أن تحتوي على حرف واحد على الأقل')
      .regex(/[0-9]/, 'يجب أن تحتوي على رقم واحد على الأقل'),
    confirm: z.string().min(1, 'أعد إدخال كلمة المرور'),
  })
  .refine((values) => values.password === values.confirm, {
    message: 'كلمتا المرور غير متطابقتين',
    path: ['confirm'],
  })

type ResetValues = z.infer<typeof schema>

const STRENGTH_LABELS = ['ضعيفة جداً', 'ضعيفة', 'متوسطة', 'قوية', 'قوية جداً'] as const
const STRENGTH_COLORS = [
  'var(--critical)',
  'var(--critical)',
  'var(--warning)',
  'var(--success)',
  'var(--success)',
] as const

function scorePassword(value: string): number {
  let score = 0
  if (value.length >= 8) score++
  if (value.length >= 12) score++
  if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score++
  if (/[0-9]/.test(value)) score++
  if (/[^A-Za-z0-9]/.test(value)) score++
  return Math.min(score, 5)
}

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [serverError, setServerError] = useState<string | null>(null)

  // No backend to validate a real token, so `?invalid=1` reaches the expired-link state.
  const token = searchParams.get('invalid') ? 'invalid' : 'demo-token'
  const linkExpired = token === 'invalid'

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ResetValues>({
    resolver: zodResolver(schema),
    defaultValues: { password: '', confirm: '' },
  })

  const password = watch('password')
  const strength = scorePassword(password ?? '')

  async function onSubmit(values: ResetValues) {
    setServerError(null)
    try {
      await resetPassword(token, values.password)
      navigate('/reset-password/success', { replace: true })
    } catch (error) {
      setServerError(error instanceof Error ? error.message : 'تعذّر تحديث كلمة المرور')
    }
  }

  if (linkExpired) {
    return (
      <AuthLayout>
        <div
          className={styles.successIcon}
          style={{ background: 'var(--critical-tint)', color: 'var(--critical-dark)' }}
        >
          <LinkIcon size={28} strokeWidth={1.9} />
        </div>
        <h1 className={styles.formTitle}>الرابط منتهي الصلاحية</h1>
        <p className={styles.formSub}>
          رابط إعادة تعيين كلمة المرور لم يعد صالحاً. روابط إعادة التعيين تنتهي بعد 30 دقيقة من
          إرسالها. اطلب رابطاً جديداً للمتابعة.
        </p>
        <Button size="lg" block onClick={() => navigate('/forgot-password')}>
          طلب رابط جديد
        </Button>
        <p className={styles.formFooter}>
          <Link to="/login" className={styles.link}>
            العودة لتسجيل الدخول
          </Link>
        </p>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout>
      <h1 className={styles.formTitle}>تعيين كلمة مرور جديدة</h1>
      <p className={styles.formSub}>اختر كلمة مرور قوية لا تقل عن 8 أحرف وتحتوي على حروف وأرقام.</p>

      {serverError && (
        <Alert
          tone="critical"
          className={styles.formAlert}
          title="تعذّر تحديث كلمة المرور"
          description={serverError}
          onDismiss={() => setServerError(null)}
        />
      )}

      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <Field label="كلمة المرور الجديدة" error={errors.password?.message} required>
          {(props) => (
            <input
              {...props}
              {...register('password')}
              type="password"
              autoComplete="new-password"
              placeholder="••••••••"
            />
          )}
        </Field>

        {password && (
          <div className={styles.strength}>
            <div className={styles.strengthTrack}>
              {[0, 1, 2, 3, 4].map((index) => (
                <span
                  key={index}
                  className={styles.strengthSeg}
                  style={
                    index < strength
                      ? { background: STRENGTH_COLORS[Math.max(0, strength - 1)] }
                      : undefined
                  }
                />
              ))}
            </div>
            <span
              className={styles.strengthLabel}
              style={{ color: STRENGTH_COLORS[Math.max(0, strength - 1)] }}
            >
              قوة كلمة المرور: {STRENGTH_LABELS[Math.max(0, strength - 1)]}
            </span>
          </div>
        )}

        <Field label="تأكيد كلمة المرور" error={errors.confirm?.message} required>
          {(props) => (
            <input
              {...props}
              {...register('confirm')}
              type="password"
              autoComplete="new-password"
              placeholder="••••••••"
            />
          )}
        </Field>

        <Button type="submit" size="lg" block loading={isSubmitting}>
          حفظ كلمة المرور
        </Button>
      </form>

      <p className={styles.formFooter}>
        <Link to="/login" className={styles.link}>
          العودة لتسجيل الدخول
        </Link>
      </p>
    </AuthLayout>
  )
}
