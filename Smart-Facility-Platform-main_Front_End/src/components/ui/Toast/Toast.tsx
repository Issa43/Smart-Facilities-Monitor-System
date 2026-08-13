import { AlertTriangle, Check, Info, X, XCircle } from 'lucide-react'
import type { Tone } from '@/types'
import { cn } from '@/lib/cn'
import styles from './Toast.module.css'

export interface ToastItem {
  id: string
  title: string
  description?: string
  tone: Tone
}

const ICONS: Record<Tone, typeof Check> = {
  success: Check,
  critical: XCircle,
  warning: AlertTriangle,
  info: Info,
  neutral: Info,
}

interface ToastStackProps {
  toasts: ToastItem[]
  onDismiss: (id: string) => void
}

/**
 * Rendered once by ToastProvider. `aria-live="polite"` means a screen reader
 * announces each toast without interrupting whatever the user is doing.
 */
export function ToastStack({ toasts, onDismiss }: ToastStackProps) {
  return (
    <div className={styles.stack} role="status" aria-live="polite" aria-atomic="false">
      {toasts.map((toast) => {
        const IconComponent = ICONS[toast.tone]
        return (
          <div key={toast.id} className={cn(styles.toast, styles[toast.tone])}>
            <div className={styles.iconBox}>
              <IconComponent strokeWidth={2.4} />
            </div>
            <div className={styles.body}>
              <div className={styles.title}>{toast.title}</div>
              {toast.description && <div className={styles.desc}>{toast.description}</div>}
            </div>
            <button
              type="button"
              className={styles.close}
              onClick={() => onDismiss(toast.id)}
              aria-label="إغلاق الإشعار"
            >
              <X size={14} strokeWidth={2.4} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
