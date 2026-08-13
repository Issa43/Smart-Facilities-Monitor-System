import { useMemo, useState } from 'react'

/**
 * Search + single-select filter for a list page.
 *
 * Every list page in the app needs exactly this pair, so it lives here rather
 * than being re-implemented fifteen times. Filtering is client-side because the
 * mock API returns whole collections; against a paginated backend the same
 * `query` and `filter` values become request parameters instead.
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
