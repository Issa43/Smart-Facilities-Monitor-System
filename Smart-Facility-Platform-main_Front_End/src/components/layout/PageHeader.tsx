import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { useCurrentUser } from '@/context/AuthContext'
import { ROLE_ROUTES, activeNavItem } from '@/routes/routeConfig'
import styles from './AppShell.module.css'

export interface Crumb {
  label: string
  to?: string
}

/**
 * Breadcrumbs derive from ROLE_ROUTES, so a nav rename updates the trail with
 * no second edit. Detail pages pass `extra` for the crumbs the config cannot
 * know — a project's name, an incident's reference.
 */
function Breadcrumbs({ extra }: { extra?: Crumb[] }) {
  const user = useCurrentUser()
  const { pathname } = useLocation()
  const config = ROLE_ROUTES[user.role]
  const current = activeNavItem(user.role, pathname)

  const crumbs: Crumb[] = [{ label: 'الرئيسية', to: config.homePath }]

  if (current && current.path !== config.homePath) {
    crumbs.push({ label: current.label, to: extra?.length ? current.path : undefined })
  }
  if (extra) crumbs.push(...extra)

  return (
    <nav className={styles.crumbs} aria-label="مسار التنقل">
      {crumbs.map((crumb, index) => {
        const isLast = index === crumbs.length - 1
        return (
          <span key={`${crumb.label}-${index}`} style={{ display: 'contents' }}>
            {index > 0 && <ChevronLeft size={13} className={styles.crumbSep} aria-hidden="true" />}
            {crumb.to && !isLast ? (
              <Link to={crumb.to} className={styles.crumbLink}>
                {crumb.label}
              </Link>
            ) : (
              <span
                className={isLast ? styles.crumbCurrent : undefined}
                aria-current={isLast ? 'page' : undefined}
              >
                {crumb.label}
              </span>
            )}
          </span>
        )
      })}
    </nav>
  )
}

interface PageHeaderProps {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  /** Extra breadcrumb entries beyond what the route config provides. */
  crumbs?: Crumb[]
}

/** The header every page opens with: breadcrumbs, title, description, actions. */
export function PageHeader({ title, description, actions, crumbs }: PageHeaderProps) {
  return (
    <>
      <Breadcrumbs extra={crumbs} />
      <div className={styles.pageHead}>
        <div>
          <h1 className={styles.pageTitle}>{title}</h1>
          {description && <p className={styles.pageDesc}>{description}</p>}
        </div>
        {actions && <div className={styles.pageActions}>{actions}</div>}
      </div>
    </>
  )
}
