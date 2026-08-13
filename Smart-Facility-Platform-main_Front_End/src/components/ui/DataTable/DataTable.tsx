import { useMemo, useState, type ReactNode } from 'react'
import { ChevronDown, ChevronsUpDown, ChevronUp } from 'lucide-react'
import { cn } from '@/lib/cn'
import { Skeleton, StateCard } from '@/components/ui/Feedback/Feedback'
import styles from './DataTable.module.css'

export interface Column<T> {
  key: string
  header: ReactNode
  /** Cell renderer. */
  render: (row: T) => ReactNode
  /** Return a comparable value to make the column sortable. */
  sortValue?: (row: T) => string | number
  /** Right-aligns and applies tabular numerals. */
  numeric?: boolean
  width?: string
}

interface DataTableProps<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  onRowClick?: (row: T) => void
  loading?: boolean
  /** Shown when `rows` is empty and not loading. */
  empty?: ReactNode
  /** Wraps the table in its own card. Off when it already sits inside a Panel. */
  card?: boolean
  className?: string
}

/**
 * The table used by every list page. Sorting is local because the mock API
 * returns whole collections; against a real paginated endpoint the same
 * `sortValue` contract becomes an `?ordering=` query parameter.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  loading,
  empty,
  card = true,
  className,
}: DataTableProps<T>) {
  const [sort, setSort] = useState<{ key: string; dir: 'asc' | 'desc' } | null>(null)

  const sorted = useMemo(() => {
    if (!sort) return rows
    const column = columns.find((c) => c.key === sort.key)
    if (!column?.sortValue) return rows

    const { sortValue } = column
    return rows.slice().sort((a, b) => {
      const left = sortValue(a)
      const right = sortValue(b)
      const result =
        typeof left === 'number' && typeof right === 'number'
          ? left - right
          : String(left).localeCompare(String(right), 'ar')
      return sort.dir === 'asc' ? result : -result
    })
  }, [rows, sort, columns])

  function toggleSort(key: string) {
    setSort((current) =>
      current?.key === key
        ? { key, dir: current.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: 'asc' },
    )
  }

  const body = (
    <div className={styles.scroll}>
      <table className={cn(styles.table, onRowClick && styles.clickable)}>
        <thead>
          <tr>
            {columns.map((column) => {
              const isSorted = sort?.key === column.key
              return (
                <th
                  key={column.key}
                  style={column.width ? { width: column.width } : undefined}
                  className={cn(
                    column.sortValue && styles.sortable,
                    column.numeric && styles.numeric,
                  )}
                  aria-sort={
                    isSorted ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined
                  }
                >
                  {column.sortValue ? (
                    <button
                      type="button"
                      className={styles.sortButton}
                      onClick={() => toggleSort(column.key)}
                    >
                      {column.header}
                      {isSorted ? (
                        sort.dir === 'asc' ? (
                          <ChevronUp size={13} className={styles.sortIconActive} />
                        ) : (
                          <ChevronDown size={13} className={styles.sortIconActive} />
                        )
                      ) : (
                        <ChevronsUpDown size={13} className={styles.sortIcon} />
                      )}
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {loading
            ? Array.from({ length: 5 }, (_, rowIndex) => (
                <tr key={`skeleton-${rowIndex}`}>
                  {columns.map((column) => (
                    <td key={column.key}>
                      <Skeleton height={12} width="70%" />
                    </td>
                  ))}
                </tr>
              ))
            : sorted.map((row) => (
                <tr
                  key={rowKey(row)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                  onKeyDown={
                    onRowClick
                      ? (event) => {
                          if (event.key === 'Enter') onRowClick(row)
                        }
                      : undefined
                  }
                >
                  {columns.map((column) => (
                    <td key={column.key} className={cn(column.numeric && styles.numeric)}>
                      {column.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  )

  const isEmpty = !loading && sorted.length === 0
  const content = isEmpty
    ? (empty ?? <StateCard bare title="لا توجد بيانات" description="لا توجد سجلات مطابقة." />)
    : body

  return card ? (
    <div className={cn(styles.card, className)}>{content}</div>
  ) : (
    <div className={className}>{content}</div>
  )
}
