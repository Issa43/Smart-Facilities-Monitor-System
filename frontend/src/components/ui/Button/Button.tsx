import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/cn'
import styles from './Button.module.css'

export type ButtonVariant = 'primary' | 'accent' | 'ghost' | 'subtle' | 'critical' | 'success'
export type ButtonSize = 'sm' | 'md' | 'lg'

interface CommonProps {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  block?: boolean
  className?: string
  children?: ReactNode
}

function classesFor({ variant = 'primary', size = 'md', loading, block, className }: CommonProps) {
  return cn(
    styles.btn,
    styles[variant],
    size !== 'md' && styles[size],
    block && styles.block,
    loading && styles.loading,
    className,
  )
}

type ButtonProps = CommonProps & ButtonHTMLAttributes<HTMLButtonElement>

export function Button({
  variant,
  size,
  loading,
  block,
  className,
  children,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={classesFor({ variant, size, loading, block, className })}
      disabled={disabled ?? loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {children}
    </button>
  )
}

/** Same visual language, but renders an <a> so navigation stays a real link. */
export function LinkButton({
  to,
  variant,
  size,
  block,
  className,
  children,
  ...rest
}: CommonProps & { to: string } & Omit<React.ComponentProps<typeof Link>, 'to' | 'className'>) {
  return (
    <Link to={to} className={classesFor({ variant, size, block, className })} {...rest}>
      {children}
    </Link>
  )
}

/**
 * Circular icon button. `label` is required — an icon alone gives a screen
 * reader nothing to announce.
 */
export function IconButton({
  label,
  size = 'md',
  className,
  children,
  type = 'button',
  ...rest
}: Omit<ButtonProps, 'variant' | 'block'> & { label: string }) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={cn(styles.btn, styles.iconOnly, size === 'sm' && styles.sm, className)}
      {...rest}
    >
      {children}
    </button>
  )
}
