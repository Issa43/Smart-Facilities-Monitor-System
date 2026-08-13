import { useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from '@/lib/cn'
import styles from './Modal.module.css'

interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  subtitle?: string
  /** Rendered in the footer — usually a cancel + confirm pair. */
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg'
  children: ReactNode
}

/**
 * Portal-rendered dialog. Handles the three things a hand-rolled modal usually
 * gets wrong: Escape to close, focus moved into the dialog on open, and the
 * page behind it not scrolling.
 */
export function Modal({
  open,
  onClose,
  title,
  subtitle,
  footer,
  size = 'md',
  children,
}: ModalProps) {
  const titleId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    // Move focus into the dialog so keyboard users are not left behind it.
    const focusTarget = dialogRef.current?.querySelector<HTMLElement>(
      'input, select, textarea, button, [href], [tabindex]:not([tabindex="-1"])',
    )
    focusTarget?.focus()

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div
      className={styles.backdrop}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        ref={dialogRef}
        className={cn(styles.modal, size !== 'md' && styles[size])}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className={styles.head}>
          <div>
            <h2 className={styles.title} id={titleId}>
              {title}
            </h2>
            {subtitle && <p className={styles.sub}>{subtitle}</p>}
          </div>
          <button type="button" className={styles.close} onClick={onClose} aria-label="إغلاق">
            <X size={18} strokeWidth={2.2} />
          </button>
        </header>

        <div className={styles.body}>{children}</div>

        {footer && <footer className={styles.foot}>{footer}</footer>}
      </div>
    </div>,
    document.body,
  )
}
