import { useCallback, useState } from 'react'
import type { ViewMode } from '@/components/ui/Controls/Controls'

/**
 * Remembers a list page's grid/list preference across visits.
 *
 * Keyed per page, so choosing "list" for projects does not silently change how
 * assets render. Persisted because re-picking the same view on every visit is
 * the kind of small friction that makes an app feel unfinished.
 */
export function useViewMode(
  pageKey: string,
  initial: ViewMode = 'grid',
): [ViewMode, (mode: ViewMode) => void] {
  const storageKey = `nozom.view.${pageKey}`

  const [mode, setModeState] = useState<ViewMode>(() => {
    const stored = localStorage.getItem(storageKey)
    return stored === 'grid' || stored === 'list' ? stored : initial
  })

  const setMode = useCallback(
    (next: ViewMode) => {
      setModeState(next)
      localStorage.setItem(storageKey, next)
    },
    [storageKey],
  )

  return [mode, setMode]
}
