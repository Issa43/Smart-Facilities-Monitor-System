import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ArrowRight, Copy, ExternalLink, KeyRound } from 'lucide-react'
import { generateDevPasswordResetLink } from '@/api/auth'
import { ApiError, API_BASE_URL } from '@/api/client'
import { useToast } from '@/context/ToastContext'
import { Button } from '@/components/ui/Button/Button'
import { Field } from '@/components/ui/Field/Field'
import { Alert } from '@/components/ui/Feedback/Feedback'
import { AuthLayout } from '../AuthLayout'
import styles from '../Auth.module.css'

const schema = z.object({
  email: z
    .string()
    .trim()
    .min(1, 'أدخل البريد الإلكتروني')
    .email('صيغة البريد الإلكتروني غير صحيحة'),
})

type DevResetValues = z.infer<typeof schema>

const GENERATE_FAILED = 'تعذّر إنشاء رابط إعادة تعيين كلمة المرور.'

/** A request that never reached the API — the browser blocked it or nothing
 *  answered. `ApiError.status === 0` is how the client reports that. The usual
 *  local cause is the dev server running on a port the backend's CORS
 *  allow-list does not name, so say which origin was actually contacted. */
function failureDetail(error: unknown): string {
  if (error instanceof ApiError && error.status === 0) {
    return `تعذّر الوصول إلى الخادم على ${API_BASE_URL}. تأكد من تشغيل الواجهة الخلفية، ومن أن هذه الصفحة مفتوحة على http://localhost:5173.`
  }
  return error instanceof Error && error.message ? error.message : GENERATE_FAILED
}

/**
 * Local-development shortcut that generates a password-reset link directly.
 *
 * No email is involved: the backend mints the link and returns it in the
 * response, so nothing is sent over SMTP and no mail inbox has to be opened.
 * The link it shows is the ordinary reset link, and the password is still
 * changed by the normal `/reset-password` page. The backend refuses this
 * request unless it runs with DEBUG on, so the page cannot work in production.
 */
export function DevPasswordResetPage() {
  const [resetUrl, setResetUrl] = useState<string | null>(null)
  const [serverError, setServerError] = useState<string | null>(null)
  const { showToast } = useToast()

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<DevResetValues>({ resolver: zodResolver(schema), defaultValues: { email: '' } })

  async function onSubmit(values: DevResetValues) {
    setServerError(null)
    setResetUrl(null)
    try {
      setResetUrl(await generateDevPasswordResetLink(values.email))
    } catch (error) {
      setServerError(failureDetail(error))
    }
  }

  async function copyLink() {
    if (!resetUrl) return
    try {
      await navigator.clipboard.writeText(resetUrl)
      showToast({ tone: 'success', title: 'تم نسخ الرابط' })
    } catch {
      // Clipboard access is blocked outside a secure context or without
      // permission; the link stays selectable on screen.
      showToast({ tone: 'critical', title: 'تعذّر النسخ، انسخ الرابط يدوياً' })
    }
  }

  return (
    <AuthLayout>
      <div className={styles.successIcon}>
        <KeyRound size={28} strokeWidth={1.9} />
      </div>
      <h1 className={styles.formTitle}>إعادة تعيين كلمة المرور — أداة تطوير</h1>
      <p className={styles.formSub}>
        اختصار للتطوير المحلي فقط: يُنشئ رابط إعادة تعيين كلمة المرور ويعرضه هنا مباشرةً. لا يتم
        إرسال أي بريد إلكتروني. تغيير كلمة المرور نفسه يتم عبر صفحة إعادة التعيين المعتادة.
      </p>

      <Alert
        tone="warning"
        className={styles.formAlert}
        title="بيئة التطوير المحلية فقط"
        description="هذه الأداة غير متاحة في بيئة الإنتاج؛ يرفضها الخادم عندما يكون DEBUG مُعطّلاً."
      />

      {serverError && (
        <Alert
          tone="critical"
          className={styles.formAlert}
          title={GENERATE_FAILED}
          description={serverError}
          onDismiss={() => setServerError(null)}
        />
      )}

      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <Field
          label="البريد الإلكتروني"
          error={errors.email?.message}
          hint="بريد حساب نشط موجود في قاعدة البيانات المحلية"
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
          إنشاء رابط إعادة التعيين
        </Button>
      </form>

      {resetUrl && (
        <div className={styles.formAlert}>
          <Alert
            tone="success"
            title="تم إنشاء رابط إعادة تعيين كلمة المرور بنجاح."
            description="الرابط صالح لمدة 30 دقيقة ويُستخدم مرة واحدة."
          />
          <p
            className={styles.formSub}
            dir="ltr"
            style={{ wordBreak: 'break-all', textAlign: 'left' }}
            data-testid="dev-reset-url"
          >
            {resetUrl}
          </p>
          <Button size="lg" block onClick={() => window.open(resetUrl, '_self')}>
            <ExternalLink size={16} strokeWidth={1.9} /> فتح صفحة إعادة التعيين
          </Button>
          <Button variant="ghost" size="lg" block onClick={copyLink}>
            <Copy size={16} strokeWidth={1.9} /> نسخ الرابط
          </Button>
        </div>
      )}

      <p className={styles.formFooter}>
        <Link to="/forgot-password" className={styles.link}>
          <ArrowRight size={13} style={{ display: 'inline', verticalAlign: '-2px' }} /> المسار
          المعتاد عبر البريد الإلكتروني
        </Link>
      </p>
    </AuthLayout>
  )
}
