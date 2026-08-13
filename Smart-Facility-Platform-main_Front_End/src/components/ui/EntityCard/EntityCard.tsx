import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/cn'
import { Icon, type IconName } from '@/components/icons'
import { ProgressBar } from '@/components/ui/Feedback/Feedback'
import styles from './EntityCard.module.css'

export function EntityGrid({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn(styles.grid, className)}>{children}</div>
}

interface EntityCardProps {
  to: string
  title: string
  icon?: IconName
  /** Rendered top-left over the media area — normally a status Badge. */
  badge?: ReactNode
  /** A CSS gradient for the media area; falls back to the brand gradient. */
  media?: string
  /** Lines of secondary information. */
  meta?: ReactNode[]
  /** Shows a labelled progress bar when provided. */
  progress?: number
  progressLabel?: string
  footer?: ReactNode
  className?: string
}

/** The card used for projects, facilities, assets, incidents and alerts. */
export function EntityCard({
  to,
  title,
  icon = 'projects',
  badge,
  media,
  meta,
  progress,
  progressLabel = 'نسبة الإنجاز',
  footer,
  className,
}: EntityCardProps) {
  return (
    <Link to={to} className={cn(styles.card, className)}>
      <div className={styles.media} style={media ? { background: media } : undefined}>
        <Icon name={icon} size={40} />
        {badge && <div className={styles.badge}>{badge}</div>}
      </div>

      <div className={styles.body}>
        <h3 className={styles.title}>{title}</h3>

        {meta && meta.length > 0 && (
          <div className={styles.metaRow}>
            {meta.map((line, index) => (
              <div key={index} className={styles.meta}>
                {line}
              </div>
            ))}
          </div>
        )}

        {progress !== undefined && (
          <>
            <div className={styles.progressRow}>
              <span>{progressLabel}</span>
              <span>{progress}%</span>
            </div>
            <ProgressBar value={progress} size="sm" label={progressLabel} />
          </>
        )}

        {footer && <div className={styles.foot}>{footer}</div>}
      </div>
    </Link>
  )
}
