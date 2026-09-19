import { NavLink, Link } from 'react-router-dom'
import { ChevronsLeft, ChevronsRight } from 'lucide-react'
import { ROLE_LABELS } from '@/types'
import { cn } from '@/lib/cn'
import { useCurrentUser } from '@/context/AuthContext'
import { ROLE_ROUTES } from '@/routes/routeConfig'
import { BrandMark, Icon } from '@/components/icons'
import { Avatar } from '@/components/ui/Display/Display'
import styles from './AppShell.module.css'

interface SidebarProps {
  collapsed: boolean
  onToggleCollapsed: () => void
  mobileOpen: boolean
  onCloseMobile: () => void
}

/** Renders entirely from ROLE_ROUTES — there is no per-role sidebar markup. */
export function Sidebar({ collapsed, onToggleCollapsed, mobileOpen, onCloseMobile }: SidebarProps) {
  const user = useCurrentUser()
  const config = ROLE_ROUTES[user.role]

  return (
    <aside
      className={cn(styles.sidebar, collapsed && styles.collapsed, mobileOpen && styles.mobileOpen)}
      aria-label="القائمة الرئيسية"
    >
      <div className={styles.brand}>
        <BrandMark />
        {!collapsed && (
          <div className={styles.brandText}>
            <div className={styles.brandName}>نُظم</div>
            <div className={styles.brandSub}>إدارة دورة حياة المنشآت</div>
          </div>
        )}
      </div>

      <Link to="/profile" className={styles.identity} onClick={onCloseMobile}>
        <Avatar initials={user.initials} size={34} />
        {!collapsed && (
          <div className={styles.identityText}>
            <div className={styles.identityName}>{user.fullName}</div>
            <div className={styles.identityRole}>{ROLE_LABELS[user.role]}</div>
          </div>
        )}
      </Link>

      <nav className={styles.nav}>
        {config.nav.map((group) => (
          <div key={group.title} className={styles.navGroup}>
            <div className={styles.navTitle}>{group.title}</div>
            {group.items.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={onCloseMobile}
                title={collapsed ? item.label : undefined}
                className={({ isActive }) => cn(styles.navItem, isActive && styles.navItemActive)}
              >
                <span className={styles.navIcon}>
                  <Icon name={item.icon} />
                </span>
                {!collapsed && <span className={styles.navLabel}>{item.label}</span>}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <button
        type="button"
        className={styles.collapseBtn}
        onClick={onToggleCollapsed}
        aria-label={collapsed ? 'توسيع القائمة' : 'طي القائمة'}
        title={collapsed ? 'توسيع القائمة' : 'طي القائمة'}
      >
        {collapsed ? <ChevronsLeft size={16} /> : <ChevronsRight size={16} />}
      </button>
    </aside>
  )
}
