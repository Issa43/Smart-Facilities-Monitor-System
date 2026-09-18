import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { ROLE_ROUTES } from '@/routes/routeConfig'
import { BrandMark } from '@/components/icons'
import { LinkButton } from '@/components/ui/Button/Button'
import styles from './NotFound.module.css'

/**
 * Rendered outside the app shell, because a bad URL may not belong to any role
 * — and a signed-out visitor has no sidebar to render around it.
 */
export function NotFoundPage() {
  const { user } = useAuth()
  const home = user ? ROLE_ROUTES[user.role].homePath : '/login'

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.brand}>
          <BrandMark size={30} />
          <span className={styles.brandName}>نُظم</span>
        </div>

        <div className={styles.iconBox}>
          <Compass size={30} strokeWidth={1.7} />
        </div>

        <h1 className={styles.code}>404</h1>
        <h2 className={styles.title}>الصفحة غير موجودة</h2>
        <p className={styles.body}>
          الرابط الذي فتحته غير صحيح أو أن الصفحة لم تعد متاحة. تحقّق من العنوان، أو عد إلى لوحة
          التحكم الخاصة بدورك الوظيفي.
        </p>

        <div className={styles.actions}>
          <LinkButton to={home} size="lg">
            {user ? 'العودة للوحة التحكم' : 'تسجيل الدخول'}
          </LinkButton>
          {user && (
            <Link to="/help" className={styles.helpLink}>
              مركز المساعدة
            </Link>
          )}
        </div>
      </div>
    </div>
  )
}
