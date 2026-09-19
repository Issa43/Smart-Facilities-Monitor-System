import type { ReactNode } from 'react'
import { BrandMark } from '@/components/icons'
import styles from './Auth.module.css'

/**
 * The split-screen shell shared by all four auth pages: brand panel on the
 * reading-start side, form on the other. Below 900px the brand panel collapses
 * to a compact header so the form stays above the fold on a phone.
 */
export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className={styles.layout}>
      <div className={styles.brandPanel}>
        <div className={styles.brandTop}>
          <div className={styles.brandLogo}>
            <span className={styles.brandLogoMark}>
              <BrandMark size={28} />
            </span>
            <span>
              <span className={styles.brandName}>نُظم</span>
              <span className={styles.brandTagline}>Smart Facility Lifecycle</span>
            </span>
          </div>
        </div>

        <div className={styles.brandMiddle}>
          <h1 className={styles.brandHeadline}>إدارة دورة حياة المنشآت في نظام واحد</h1>
          <p className={styles.brandBody}>
            من أول يوم في موقع الإنشاء وحتى التشغيل اليومي — تابع مراحل التنفيذ، والمواد، والجودة،
            والأصول، وأعمال الصيانة، والحوادث الأمنية، من منصة مركزية واحدة.
          </p>

          <div className={styles.brandStats}>
            <div className={styles.brandStat}>
              <div className={styles.brandStatValue}>4</div>
              <div className={styles.brandStatLabel}>أدوار وظيفية</div>
            </div>
            <div className={styles.brandStat}>
              <div className={styles.brandStatValue}>2</div>
              <div className={styles.brandStatLabel}>مرحلتا إنشاء وتشغيل</div>
            </div>
            <div className={styles.brandStat}>
              <div className={styles.brandStatValue}>60+</div>
              <div className={styles.brandStatLabel}>شاشة تشغيلية</div>
            </div>
          </div>
        </div>

        <div className={styles.brandBottom}>
          <p className={styles.brandFooter}>
            مشروع تخرج — منصة إدارة دورة حياة المنشآت · {new Date().getFullYear()}
          </p>
        </div>
      </div>

      <div className={styles.formPanel}>
        <div className={styles.formInner}>{children}</div>
      </div>
    </div>
  )
}
