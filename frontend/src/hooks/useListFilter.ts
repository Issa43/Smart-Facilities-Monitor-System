import { useMemo, useState } from 'react'

/**
 * Search + single-select filter for a list page.
 *
 * Shared search + filter state for bounded or already-scoped API collections.
 * High-volume list screens should pass these values to their backend query
 * rather than applying this helper to an unbounded collection.
 */
export function useListFilter<T, F extends string>(
  items: T[] | undefined,
  options: {
    /** Text a row is searchable by — matched case-insensitively. */
    searchText: (item: T) => string
    /** Whether an item belongs to the given filter value. */
    matchesFilter?: (item: T, filter: F) => boolean
    /** The filter value meaning "show everything". */
    allValue: F
  },
) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<F>(options.allValue)

  const { searchText, matchesFilter, allValue } = options

  const filtered = useMemo(() => {
    const list = items ?? []
    const needle = query.trim().toLowerCase()

    return list.filter((item) => {
      if (filter !== allValue && matchesFilter && !matchesFilter(item, filter)) return false
      if (!needle) return true
      return searchText(item).toLowerCase().includes(needle)
    })
  }, [items, query, filter, searchText, matchesFilter, allValue])

  return { query, setQuery, filter, setFilter, filtered }
}
