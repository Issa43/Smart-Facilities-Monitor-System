import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ArrowRight, MailCheck } from 'lucide-react'
import { generateDevPasswordResetLink, requestPasswordReset } from '@/api/auth'
import { useToast } from '@/context/ToastContext'
import { Button } from '@/components/ui/Button/Button'
import { Field } from '@/components/ui/Field/Field'
import { Alert } from '@/components/ui/Feedback/Feedback'
import { AuthLayout } from '../AuthLayout'
import { followResetLink } from '../resetLinkNavigation'
import styles from '../Auth.module.css'

/**
 * Local development has no mailbox to check, so the same page instead asks the
 * backend for the link and follows it straight to the reset form. The bundler
 * resolves this constant at build time and drops the branch it disables, so a
 * production bundle contains neither the dev call nor its wording.
 */
const DIRECT_LINK = import.meta.env.DEV

const schema = z.object({
  email: z
    .string()
    .trim()
    .min(1, 'أدخل البريد الإلكتروني')
    .email('صيغة البريد الإلكتروني غير صحيحة'),
})

type ForgotValues = z.infer<typeof schema>

/**
 * One page, two states: the request form, then the "check your email" screen.
 *
 * In local development the second state never appears — there is no mailbox to
 * check, so the page follows the generated link to `/reset-password` itself.
 */
export function ForgotPasswordPage() {
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [serverError, setServerError] = useState<string | null>(null)
  const { showToast } = useToast()
  const navigate = useNavigate()

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotValues>({ resolver: zodResolver(schema), defaultValues: { email: '' } })

  async function onSubmit(values: ForgotValues) {
    setServerError(null)
    try {
      if (DIRECT_LINK) {
        // Nothing is emailed here, so the user is taken to the reset form
        // rather than being told to go looking for a message.
        followResetLink(await generateDevPasswordResetLink(values.email), navigate)
        return
      }
      await requestPasswordReset(values.email)
      setSentTo(values.email)
    } catch (error) {
      const fallback = DIRECT_LINK
        ? 'تعذّر إنشاء رابط إعادة تعيين كلمة المرور.'
        : 'تعذّر إرسال رابط إعادة التعيين'
      setServerError(error instanceof Error && error.message ? error.message : fallback)
    }
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
            try {
              await requestPasswordReset(sentTo)
              showToast({ tone: 'success', title: 'تم إرسال الرابط مرة أخرى' })
            } catch (error) {
              showToast({
                tone: 'critical',
                title: 'تعذّر إعادة إرسال الرابط',
                description: error instanceof Error ? error.message : undefined,
              })
            }
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
        {DIRECT_LINK
          ? 'أدخل بريدك الإلكتروني المسجّل وسيتم نقلك مباشرةً إلى صفحة إعادة تعيين كلمة المرور.'
          : 'أدخل بريدك الإلكتروني المسجّل وسنرسل لك رابطاً لإعادة تعيين كلمة المرور.'}
      </p>

      {serverError && (
        <Alert
          tone="critical"
          className={styles.formAlert}
          title={DIRECT_LINK ? 'تعذّر إنشاء رابط إعادة تعيين كلمة المرور.' : 'تعذّر إرسال الرابط'}
          description={serverError}
          onDismiss={() => setServerError(null)}
        />
      )}

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
          {DIRECT_LINK ? 'متابعة إعادة تعيين كلمة المرور' : 'إرسال رابط إعادة التعيين'}
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
