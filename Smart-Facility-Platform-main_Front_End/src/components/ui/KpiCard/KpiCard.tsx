import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { Icon, type IconName } from '@/components/icons'
import styles from './KpiCard.module.css'

export type KpiTone = 'primary' | 'accent' | 'success' | 'warning' | 'critical' | 'info' | 'neutral'

interface KpiCardProps {
  label: string
  value: ReactNode
  icon?: IconName
  tone?: KpiTone
  /** Small line under the value — a trend, a caveat, a count. */
  footnote?: ReactNode
  footnoteTone?: 'success' | 'warning' | 'critical'
  /** Renders a progress bar instead of a footnote. 0–100. */
  progress?: number
  loading?: boolean
  className?: string
}

export function KpiCard({
  label,
  value,
  icon,
  tone = 'primary',
  footnote,
  footnoteTone,
  progress,
  loading,
  className,
}: KpiCardProps) {
  return (
    <article className={cn(styles.card, styles[tone], className)}>
      <div className={styles.top}>
        <div style={{ minWidth: 0, flex: 1 }}>
          {loading ? (
            <>
              <div className={styles.skeletonLabel} />
              <div className={styles.skeletonValue} />
            </>
          ) : (
            <>
              <div className={styles.label}>{label}</div>
              <div className={styles.value}>{value}</div>
            </>
          )}
        </div>
        {icon && (
          <div className={styles.iconBox}>
            <Icon name={icon} />
          </div>
        )}
      </div>

      {!loading && progress !== undefined && (
        <div
          className={styles.bar}
          role="progressbar"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={label}
        >
          <span style={{ width: `${Math.min(100, Math.max(0, progress))}%` }} />
        </div>
      )}

      {!loading && progress === undefined && footnote && (
        <div
          className={cn(
            styles.foot,
            footnoteTone === 'success' && styles.footSuccess,
            footnoteTone === 'warning' && styles.footWarning,
            footnoteTone === 'critical' && styles.footCritical,
          )}
        >
          {footnote}
        </div>
      )}
    </article>
  )
}
