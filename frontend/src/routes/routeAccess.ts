import type { Role } from '@/types'

export function canAccessRoleRoute(userRole: Role, routeRole: Role): boolean {
  return userRole === 'super_admin' || userRole === routeRole
}
