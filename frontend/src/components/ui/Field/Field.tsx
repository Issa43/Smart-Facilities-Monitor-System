import { useId, type ReactNode } from 'react'
import { AlertCircle } from 'lucide-react'
import { cn } from '@/lib/cn'
import styles from './Field.module.css'

interface FieldProps {
  label: string
  /** Validation message from react-hook-form. Presence switches the field to its error state. */
  error?: string
  hint?: string
  required?: boolean
  className?: string
  /** Receives the id and aria wiring to spread onto the input. */
  children: (props: {
    id: string
    'aria-invalid': boolean
    'aria-describedby': string | undefined
  }) => ReactNode
}

/**
 * Wraps a native input/select/textarea with a label, hint and error message,
 * and wires up the aria attributes that connect them.
 *
 * The render-prop shape is deliberate: it keeps the actual control native
 * (so react-hook-form's `register` works unchanged) while guaranteeing the
 * accessibility plumbing is never forgotten.
 */
export function Field({ label, error, hint, required, className, children }: FieldProps) {
  const id = useId()
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const describedBy = error ? errorId : hint ? hintId : undefined

  return (
    <div className={cn(styles.field, error && styles.hasError, className)}>
      <label className={styles.label} htmlFor={id}>
        {label}
        {required && (
          <span className={styles.required} aria-hidden="true">
            *
          </span>
        )}
      </label>

      {children({ id, 'aria-invalid': Boolean(error), 'aria-describedby': describedBy })}

      {hint && !error && (
        <p className={styles.hint} id={hintId}>
          {hint}
        </p>
      )}
      {error && (
        <p className={styles.error} id={errorId}>
          <AlertCircle size={12} strokeWidth={2.4} />
          {error}
        </p>
      )}
    </div>
  )
}

/** Two fields side by side, stacking below 700px. */
export function FieldRow({ children, cols = 2 }: { children: ReactNode; cols?: 2 | 3 }) {
  return <div className={cols === 3 ? styles.row3 : styles.row}>{children}</div>
}
