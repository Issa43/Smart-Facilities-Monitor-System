import type { ReactNode } from 'react'
import { LayoutGrid, List, Search, X } from 'lucide-react'
import { cn } from '@/lib/cn'
import { formatNumber } from '@/lib/format'
import styles from './Controls.module.css'

/** The row above a list: search + filters on one side, actions on the other. */
export function Toolbar({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn(styles.toolbar, className)}>{children}</div>
}

/* ==========================================================================
   Filter pills
   ========================================================================== */

export interface FilterOption<T extends string> {
  value: T
  label: string
  count?: number
}

interface FilterBarProps<T extends string> {
  options: FilterOption<T>[]
  value: T
  onChange: (value: T) => void
  /** Announced to screen readers, e.g. "تصفية المشاريع حسب الحالة". */
  label: string
  className?: string
}

export function FilterBar<T extends string>({
  options,
  value,
  onChange,
  label,
  className,
}: FilterBarProps<T>) {
  return (
    <div className={cn(styles.filterBar, className)} role="group" aria-label={label}>
      {options.map((option) => {
        const isActive = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            className={cn(styles.filter, isActive && styles.filterActive)}
            aria-pressed={isActive}
            onClick={() => onChange(option.value)}
          >
            {option.label}
            {option.count !== undefined && (
              <span className={styles.filterCount}>{formatNumber(option.count)}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}

/* ==========================================================================
   Search
   ========================================================================== */

interface SearchInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
}

export function SearchInput({ value, onChange, placeholder, className }: SearchInputProps) {
  return (
    <div className={cn(styles.search, className)}>
      <Search size={16} strokeWidth={2} aria-hidden="true" />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder ?? 'ابحث…'}
        aria-label={placeholder ?? 'بحث'}
      />
      {value && (
        <button
          type="button"
          className={styles.searchClear}
          onClick={() => onChange('')}
          aria-label="مسح البحث"
        >
          <X size={14} strokeWidth={2.4} />
        </button>
      )}
    </div>
  )
}

/* ==========================================================================
   Grid / list view toggle
   ========================================================================== */

export type ViewMode = 'grid' | 'list'

export function ViewToggle({
  value,
  onChange,
}: {
  value: ViewMode
  onChange: (value: ViewMode) => void
}) {
  return (
    <div className={styles.viewToggle} role="group" aria-label="طريقة العرض">
      <button
        type="button"
        className={cn(styles.viewBtn, value === 'grid' && styles.viewBtnActive)}
        onClick={() => onChange('grid')}
        aria-pressed={value === 'grid'}
        aria-label="عرض شبكي"
        title="عرض شبكي"
      >
        <LayoutGrid size={16} strokeWidth={2} />
      </button>
      <button
        type="button"
        className={cn(styles.viewBtn, value === 'list' && styles.viewBtnActive)}
        onClick={() => onChange('list')}
        aria-pressed={value === 'list'}
        aria-label="عرض قائمة"
        title="عرض قائمة"
      >
        <List size={16} strokeWidth={2} />
      </button>
    </div>
  )
}

/* ==========================================================================
   Switch
   ========================================================================== */

interface SwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
  disabled?: boolean
}

export function Switch({ checked, onChange, label, disabled }: SwitchProps) {
  return (
    <span className={styles.switch}>
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        aria-label={label}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className={styles.track} />
    </span>
  )
}
