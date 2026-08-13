import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/cn'
import styles from './Dropdown.module.css'

interface DropdownProps {
  /** Receives `open` so the trigger can reflect state (e.g. rotate a chevron). */
  trigger: (open: boolean) => ReactNode
  children: ReactNode
  className?: string
}

export function Dropdown({ trigger, children, className }: DropdownProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return

    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div ref={rootRef} className={cn(styles.root, className)}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        {trigger(open)}
      </button>

      {open && (
        // Closing on click lets each item skip its own setOpen(false).
        <div className={styles.menu} role="menu" onClick={() => setOpen(false)}>
          {children}
        </div>
      )}
    </div>
  )
}

export function DropdownItem({
  onClick,
  to,
  danger,
  children,
}: {
  onClick?: () => void
  to?: string
  danger?: boolean
  children: ReactNode
}) {
  const className = cn(styles.item, danger && styles.danger)

  if (to) {
    return (
      <Link to={to} className={className} role="menuitem">
        {children}
      </Link>
    )
  }

  return (
    <button type="button" className={className} role="menuitem" onClick={onClick}>
      {children}
    </button>
  )
}

export function DropdownDivider() {
  return <div className={styles.divider} role="separator" />
}
