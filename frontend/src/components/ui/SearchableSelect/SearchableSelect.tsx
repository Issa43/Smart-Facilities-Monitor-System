import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, Search } from 'lucide-react'
import { cn } from '@/lib/cn'
import styles from './SearchableSelect.module.css'

export interface SearchableSelectOption {
  value: string
  label: string
  description?: string
  keywords?: string
}

interface SearchableSelectProps {
  id?: string
  value: string
  onChange: (value: string) => void
  options: SearchableSelectOption[]
  placeholder: string
  loading?: boolean
  error?: boolean
  emptyMessage?: string
  disabled?: boolean
  'aria-invalid'?: boolean
  'aria-describedby'?: string
}

const normalize = (value: string) => value.trim().toLocaleLowerCase()

export function SearchableSelect({
  id,
  value,
  onChange,
  options,
  placeholder,
  loading = false,
  error = false,
  emptyMessage = 'لا توجد خيارات متاحة',
  disabled = false,
  'aria-invalid': ariaInvalid,
  'aria-describedby': ariaDescribedBy,
}: SearchableSelectProps) {
  const selected = options.find((option) => option.value === value)
  const [query, setQuery] = useState(selected?.label ?? '')
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)

  useEffect(() => {
    setQuery(selected?.label ?? '')
  }, [selected?.label])

  const filtered = useMemo(() => {
    const needle = normalize(query)
    if (!needle || selected?.label === query) return options
    return options.filter((option) =>
      normalize(`${option.label} ${option.description ?? ''} ${option.keywords ?? ''}`).includes(
        needle,
      ),
    )
  }, [options, query, selected?.label])

  const choose = (option: SearchableSelectOption) => {
    onChange(option.value)
    setQuery(option.label)
    setOpen(false)
  }

  const unavailableMessage = loading
    ? 'جارٍ تحميل الخيارات…'
    : error
      ? 'تعذّر تحميل الخيارات'
      : filtered.length === 0
        ? emptyMessage
        : null

  return (
    <div className={styles.root}>
      <Search className={styles.searchIcon} size={16} aria-hidden="true" />
      <input
        id={id}
        type="search"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={id ? `${id}-options` : undefined}
        aria-invalid={ariaInvalid}
        aria-describedby={ariaDescribedBy}
        value={query}
        placeholder={placeholder}
        disabled={disabled || loading || error}
        autoComplete="off"
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 100)}
        onChange={(event) => {
          setQuery(event.target.value)
          onChange('')
          setActiveIndex(0)
          setOpen(true)
        }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') {
            event.preventDefault()
            setOpen(true)
            setActiveIndex((index) => Math.min(index + 1, filtered.length - 1))
          } else if (event.key === 'ArrowUp') {
            event.preventDefault()
            setActiveIndex((index) => Math.max(index - 1, 0))
          } else if (event.key === 'Enter' && open && filtered[activeIndex]) {
            event.preventDefault()
            choose(filtered[activeIndex])
          } else if (event.key === 'Escape') {
            setOpen(false)
          }
        }}
      />
      <ChevronDown className={styles.chevron} size={16} aria-hidden="true" />

      {open && !disabled && (
        <div className={styles.menu} id={id ? `${id}-options` : undefined} role="listbox">
          {unavailableMessage ? (
            <div className={cn(styles.state, error && styles.error)} role="status">
              {unavailableMessage}
            </div>
          ) : (
            filtered.map((option, index) => (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={option.value === value}
                className={cn(
                  styles.option,
                  index === activeIndex && styles.active,
                  option.value === value && styles.selected,
                )}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => choose(option)}
              >
                <span>{option.label}</span>
                {option.description && <small>{option.description}</small>}
              </button>
            ))
          )}
        </div>
      )}
      {!open && unavailableMessage && (
        <div
          className={cn(styles.inlineState, error && styles.error)}
          role={error ? 'alert' : 'status'}
        >
          {unavailableMessage}
        </div>
      )}
    </div>
  )
}
