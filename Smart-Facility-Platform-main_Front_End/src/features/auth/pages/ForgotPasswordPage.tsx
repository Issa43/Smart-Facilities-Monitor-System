import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ArrowRight, MailCheck } from 'lucide-react'
import { requestPasswordReset } from '@/api/auth'
import { useToast } from '@/context/ToastContext'
import { Button } from '@/components/ui/Button/Button'
import { Field } from '@/components/ui/Field/Field'
import { AuthLayout } from '../AuthLayout'
import styles from '../Auth.module.css'

const schema = z.object({
  email: z
    .string()
    .trim()
    .min(1, 'أدخل البريد الإلكتروني')
    .email('صيغة البريد الإلكتروني غير صحيحة'),
})

type ForgotValues = z.infer<typeof schema>

/** One page, two states: the request form, then the "check your email" screen. */
export function ForgotPasswordPage() {
  const [sentTo, setSentTo] = useState<string | null>(null)
  const { showToast } = useToast()

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotValues>({ resolver: zodResolver(schema), defaultValues: { email: '' } })

  async function onSubmit(values: ForgotValues) {
    await requestPasswordReset(values.email)
    setSentTo(values.email)
  }

  if (sentTo) {
    return (
      <AuthLayout>
        <div className={styles.successIcon}>
          <MailCheck size={28} strokeWidth={1.9} />
        </div>
        <h1 className={styles.formTitle}>تحقّق من بريدك الإلكتروني</h1>
        <p className={styles.formSub}>
          إذا كان هناك حساب مرتبط بـ <strong>{sentTo}</strong>، فقد أرسلنا إليه رابطاً لإعادة تعيين
          كلمة المرور. الرابط صالح لمدة 30 دقيقة.
        </p>

        <Button
          variant="ghost"
          block
          size="lg"
          onClick={async () => {
            await requestPasswordReset(sentTo)
            showToast({ tone: 'success', title: 'تم إرسال الرابط مرة أخرى' })
          }}
        >
          إعادة إرسال الرابط
        </Button>

        <p className={styles.formFooter}>
          <Link to="/login" className={styles.link}>
            <ArrowRight size={13} style={{ display: 'inline', verticalAlign: '-2px' }} /> العودة
            لتسجيل الدخول
          </Link>
        </p>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout>
      <h1 className={styles.formTitle}>نسيت كلمة المرور</h1>
      <p className={styles.formSub}>
        أدخل بريدك الإلكتروني المسجّل وسنرسل لك رابطاً لإعادة تعيين كلمة المرور.
      </p>

      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <Field
          label="البريد الإلكتروني"
          error={errors.email?.message}
          hint="نفس البريد المستخدم عند إنشاء الحساب"
          required
        >
          {(props) => (
            <input
              {...props}
              {...register('email')}
              type="email"
              autoComplete="email"
              placeholder="name@nozom.sa"
              dir="ltr"
            />
          )}
        </Field>

        <Button type="submit" size="lg" block loading={isSubmitting}>
          إرسال رابط إعادة التعيين
        </Button>
      </form>

      <p className={styles.formFooter}>
        تذكّرت كلمة المرور؟{' '}
        <Link to="/login" className={styles.link}>
          العودة لتسجيل الدخول
        </Link>
      </p>
    </AuthLayout>
  )
}
