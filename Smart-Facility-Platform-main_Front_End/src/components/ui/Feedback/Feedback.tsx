import type { CSSProperties, ReactNode } from 'react'
import { AlertCircle, AlertTriangle, CheckCircle2, Inbox, Info, X } from 'lucide-react'
import type { Tone } from '@/types'
import { cn } from '@/lib/cn'
import { formatPercent } from '@/lib/format'
import { progressTone } from '@/lib/tone'
import styles from './Feedback.module.css'

/* ==========================================================================
   Alert
   ========================================================================== */

const ALERT_ICONS: Record<Tone, typeof Info> = {
  success: CheckCircle2,
  critical: AlertCircle,
  warning: AlertTriangle,
  info: Info,
  neutral: Info,
}

interface AlertProps {
  tone?: Tone
  title: ReactNode
  description?: ReactNode
  onDismiss?: () => void
  className?: string
}

export function Alert({ tone = 'info', title, description, onDismiss, className }: AlertProps) {
  const IconComponent = ALERT_ICONS[tone]
  return (
    <div
      className={cn(styles.alert, styles[tone], className)}
      role={tone === 'critical' ? 'alert' : 'status'}
    >
      <IconComponent className={styles.alertIcon} strokeWidth={2.2} />
      <div className={styles.alertBody}>
        <div className={styles.alertTitle}>{title}</div>
        {description && <div className={styles.alertDesc}>{description}</div>}
      </div>
      {onDismiss && (
        <button
          type="button"
          className={styles.alertClose}
          onClick={onDismiss}
          aria-label="إخفاء التنبيه"
        >
          <X size={16} strokeWidth={2.2} />
        </button>
      )}
    </div>
  )
}

/* ==========================================================================
   Skeleton
   ========================================================================== */

export function Skeleton({
  width = '100%',
  height = 12,
  className,
  style,
}: {
  width?: string | number
  height?: string | number
  className?: string
  style?: CSSProperties
}) {
  return <div className={cn(styles.skeleton, className)} style={{ width, height, ...style }} />
}

/** N stacked skeleton lines — the default loading state for a list or panel body. */
export function SkeletonLines({ count = 4 }: { count?: number }) {
  return (
    <div
      style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
      role="status"
      aria-label="جارٍ التحميل"
    >
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} height={14} width={`${100 - i * 7}%`} />
      ))}
    </div>
  )
}

/* ==========================================================================
   Empty / error state
   ========================================================================== */

interface StateCardProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
  tone?: 'neutral' | 'critical'
  /** Drops the card chrome — for use inside a Panel that already has a border. */
  bare?: boolean
  className?: string
}

export function StateCard({
  icon,
  title,
  description,
  action,
  tone = 'neutral',
  bare,
  className,
}: StateCardProps) {
  return (
    <div className={cn(bare ? styles.stateBare : styles.state, className)}>
      <div className={cn(styles.stateIcon, tone === 'critical' && styles.stateIconCritical)}>
        {icon ?? <Inbox size={24} strokeWidth={1.8} />}
      </div>
      <h3 className={styles.stateTitle}>{title}</h3>
      {description && <p className={styles.stateDesc}>{description}</p>}
      {action}
    </div>
  )
}

/** The standard "this query failed" view. */
export function ErrorState({ error, bare }: { error: unknown; bare?: boolean }) {
  const message = error instanceof Error ? error.message : 'حدث خطأ غير متوقع'
  return (
    <StateCard
      tone="critical"
      bare={bare}
      icon={<AlertCircle size={24} strokeWidth={1.9} />}
      title="تعذّر تحميل البيانات"
      description={message}
    />
  )
}

/* ==========================================================================
   Progress bar
   ========================================================================== */

const TONE_COLORS: Record<Tone, string> = {
  success: 'var(--success)',
  warning: 'var(--warning)',
  critical: 'var(--critical)',
  info: 'var(--primary)',
  neutral: 'var(--border-strong)',
}

interface ProgressBarProps {
  value: number
  tone?: Tone
  size?: 'sm' | 'md'
  showValue?: boolean
  label?: string
  className?: string
}

export function ProgressBar({
  value,
  tone,
  size = 'md',
  showValue,
  label,
  className,
}: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, value))
  const color = TONE_COLORS[tone ?? progressTone(clamped)]

  const bar = (
    <div
      className={cn(styles.progress, size === 'sm' && styles.progressSm, className)}
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <span className={styles.progressFill} style={{ width: `${clamped}%`, background: color }} />
    </div>
  )

  if (!showValue) return bar

  return (
    <div className={styles.progressLabelled}>
      <div style={{ flex: 1 }}>{bar}</div>
      <span className={styles.progressValue} style={{ color }}>
        {formatPercent(clamped)}
      </span>
    </div>
  )
}
