import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Bell, ChevronDown, HelpCircle, LogOut, Menu, Search, User as UserIcon } from 'lucide-react'
import { ROLE_LABELS } from '@/types'
import { qk } from '@/lib/queryKeys'
import { listNotifications } from '@/api/users'
import { useAuth, useCurrentUser } from '@/context/AuthContext'
import { ROLE_ROUTES } from '@/routes/routeConfig'
import { Avatar } from '@/components/ui/Display/Display'
import { Dropdown, DropdownDivider, DropdownItem } from '@/components/ui/Dropdown/Dropdown'
import styles from './AppShell.module.css'

interface TopbarProps {
  onOpenMobileNav: () => void
  onOpenNotifications: () => void
}

export function Topbar({ onOpenMobileNav, onOpenNotifications }: TopbarProps) {
  const user = useCurrentUser()
  const { logout } = useAuth()
  const navigate = useNavigate()
  const config = ROLE_ROUTES[user.role]

  const { data: notifications = [] } = useQuery({
    queryKey: qk.notifications.list(user.role),
    queryFn: () => listNotifications(user.role),
  })
  const unread = notifications.filter((n) => !n.read).length

  return (
    <header className={styles.topbar}>
      <button
        type="button"
        className={styles.mobileToggle}
        onClick={onOpenMobileNav}
        aria-label="فتح القائمة"
      >
        <Menu size={20} />
      </button>

      <div className={styles.topSearch}>
        <Search size={16} strokeWidth={2} aria-hidden="true" />
        <input type="search" placeholder={config.searchPlaceholder} aria-label="بحث في النظام" />
      </div>

      <div className={styles.topActions}>
        <button
          type="button"
          className={styles.notifBtn}
          onClick={onOpenNotifications}
          aria-label={unread > 0 ? `الإشعارات، ${unread} غير مقروءة` : 'الإشعارات'}
        >
          <Bell size={19} strokeWidth={2} />
          {unread > 0 && (
            <span className={styles.notifDot} aria-hidden="true">
              {unread}
            </span>
          )}
        </button>

        <Dropdown
          trigger={() => (
            <span className={styles.profile}>
              <span className={styles.profileText}>
                <span className={styles.profileName}>{user.fullName}</span>
                <span className={styles.profileRole}>{ROLE_LABELS[user.role]}</span>
              </span>
              <Avatar initials={user.initials} />
              <ChevronDown size={15} strokeWidth={2.2} aria-hidden="true" />
            </span>
          )}
        >
          <DropdownItem to="/profile">
            <UserIcon size={15} strokeWidth={2} />
            الملف الشخصي
          </DropdownItem>
          <DropdownItem to="/help">
            <HelpCircle size={15} strokeWidth={2} />
            مركز المساعدة
          </DropdownItem>
          <DropdownDivider />
          <DropdownItem
            danger
            onClick={() => {
              logout()
              navigate('/login', { replace: true })
            }}
          >
            <LogOut size={15} strokeWidth={2} />
            تسجيل الخروج
          </DropdownItem>
        </Dropdown>
      </div>
    </header>
  )
}
