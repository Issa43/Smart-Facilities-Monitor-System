import type { ReactNode } from 'react'
import type { Tone } from '@/types'
import { cn } from '@/lib/cn'
import styles from './Badge.module.css'

interface BadgeProps {
  tone?: Tone
  /** Adds a pulsing dot — only for genuinely live states. */
  live?: boolean
  /** Hides the leading dot. */
  plain?: boolean
  className?: string
  children: ReactNode
}

export function Badge({ tone = 'neutral', live, plain, className, children }: BadgeProps) {
  return (
    <span
      className={cn(
        styles.badge,
        styles[tone],
        live && styles.live,
        plain && styles.plain,
        className,
      )}
    >
      {children}
    </span>
  )
}
