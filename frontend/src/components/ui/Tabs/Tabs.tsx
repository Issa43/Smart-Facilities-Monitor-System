import { useId, useState, type ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { formatNumber } from '@/lib/format'
import styles from './Tabs.module.css'

export interface TabDefinition {
  id: string
  label: string
  /** Optional count pill — e.g. how many rows the tab holds. */
  count?: number
  content: ReactNode
}

interface TabsProps {
  tabs: TabDefinition[]
  defaultTab?: string
  className?: string
}

/**
 * The workspace pattern used by every detail page (project, facility, asset,
 * incident). Only the active panel is mounted, so a ten-tab page does not run
 * ten queries on load.
 */
export function Tabs({ tabs, defaultTab, className }: TabsProps) {
  const baseId = useId()
  const [active, setActive] = useState(defaultTab ?? tabs[0]?.id ?? '')
  const activeTab = tabs.find((tab) => tab.id === active) ?? tabs[0]

  return (
    <div className={className}>
      <div className={styles.bar} role="tablist">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTab?.id
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`${baseId}-tab-${tab.id}`}
              aria-selected={isActive}
              aria-controls={`${baseId}-panel-${tab.id}`}
              className={cn(styles.trigger, isActive && styles.active)}
              onClick={() => setActive(tab.id)}
            >
              {tab.label}
              {tab.count !== undefined && (
                <span className={styles.count}>{formatNumber(tab.count)}</span>
              )}
            </button>
          )
        })}
      </div>

      {activeTab && (
        <div
          key={activeTab.id}
          role="tabpanel"
          id={`${baseId}-panel-${activeTab.id}`}
          aria-labelledby={`${baseId}-tab-${activeTab.id}`}
          className={styles.panel}
        >
          {activeTab.content}
        </div>
      )}
    </div>
  )
}
