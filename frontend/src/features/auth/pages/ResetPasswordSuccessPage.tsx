import { Link } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'
import { LinkButton } from '@/components/ui/Button/Button'
import { AuthLayout } from '../AuthLayout'
import styles from '../Auth.module.css'

export function ResetPasswordSuccessPage() {
  return (
    <AuthLayout>
      <div className={styles.successIcon}>
        <ShieldCheck size={30} strokeWidth={1.9} />
      </div>

      <h1 className={styles.formTitle}>تم تحديث كلمة المرور</h1>
      <p className={styles.formSub}>
        تم حفظ كلمة المرور الجديدة بنجاح. يمكنك الآن تسجيل الدخول باستخدامها. لأمان حسابك، سيتم
        إنهاء أي جلسات مفتوحة على الأجهزة الأخرى.
      </p>

      <LinkButton to="/login" size="lg" block>
        تسجيل الدخول
      </LinkButton>

      <p className={styles.formFooter}>
        تواجه مشكلة؟{' '}
        <Link to="/help" className={styles.link}>
          تواصل مع الدعم الفني
        </Link>
      </p>
    </AuthLayout>
  )
}
