import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import styles from './Panel.module.css'

interface PanelProps {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  /** Removes padding — for panels whose body is a table or a media grid. */
  flush?: boolean
  className?: string
  children: ReactNode
}

export function Panel({ title, subtitle, actions, flush, className, children }: PanelProps) {
  return (
    <section className={cn(styles.panel, flush && styles.flush, className)}>
      {(title || actions) && (
        <header className={styles.head}>
          <div>
            {title && <h2 className={styles.title}>{title}</h2>}
            {subtitle && <p className={styles.sub}>{subtitle}</p>}
          </div>
          {actions && <div className={styles.actions}>{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}
