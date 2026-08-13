import type { AppNotification, AuditLogEntry, Role, User } from '@/types'
import { badRequest, delay, newId, notFound, nowIso } from './client'
import { clone, commit, getDb } from './db'

export interface UserInput {
  fullName: string
  email: string
  phone: string
  username: string
  role: Role
  status: User['status']
}

function initialsOf(fullName: string): string {
  const parts = fullName.trim().split(/\s+/)
  const first = parts[0]?.[0] ?? '؟'
  const second = parts[1]?.[0] ?? ''
  return `${first}${second}`
}

export async function listUsers(): Promise<User[]> {
  await delay()
  return clone(getDb().users)
}

export async function getUser(id: string): Promise<User> {
  await delay()
  const user = getDb().users.find((u) => u.id === id)
  return user ? clone(user) : notFound('المستخدم')
}

export async function createUser(input: UserInput): Promise<User> {
  await delay()
  return commit((db) => {
    const taken = db.users.some(
      (u) =>
        u.username.toLowerCase() === input.username.toLowerCase() ||
        u.email.toLowerCase() === input.email.toLowerCase(),
    )
    if (taken) badRequest('اسم المستخدم أو البريد الإلكتروني مستخدم بالفعل')

    const user: User = {
      id: newId('usr'),
      ...input,
      initials: initialsOf(input.fullName),
      lastLoginAt: null,
      createdAt: nowIso(),
      hasOperationalRecords: false,
    }
    db.users.unshift(user)
    return clone(user)
  })
}

export async function updateUser(id: string, input: Partial<UserInput>): Promise<User> {
  await delay()
  return commit((db) => {
    const user = db.users.find((u) => u.id === id)
    if (!user) notFound('المستخدم')

    Object.assign(user, input)
    if (input.fullName) user.initials = initialsOf(input.fullName)
    return clone(user)
  })
}

/**
 * Requirement: a user linked to operational records may be deactivated but not
 * deleted, so historical projects, work orders and incidents keep a valid author.
 */
export async function deleteUser(id: string): Promise<void> {
  await delay()
  commit((db) => {
    const user = db.users.find((u) => u.id === id)
    if (!user) notFound('المستخدم')

    if (user.hasOperationalRecords) {
      badRequest('لا يمكن حذف مستخدم مرتبط بسجلات تشغيلية — يمكن إيقاف الحساب بدلاً من ذلك')
    }

    db.users = db.users.filter((u) => u.id !== id)
  })
}

export async function setUserStatus(id: string, status: User['status']): Promise<User> {
  await delay()
  return commit((db) => {
    const user = db.users.find((u) => u.id === id)
    if (!user) notFound('المستخدم')
    user.status = status
    return clone(user)
  })
}

export async function resetUserPassword(id: string): Promise<void> {
  await delay()
  const exists = getDb().users.some((u) => u.id === id)
  if (!exists) notFound('المستخدم')
}

/* ==========================================================================
   Notifications & audit log — cross-cutting, so they live here
   ========================================================================== */

export async function listNotifications(role: Role): Promise<AppNotification[]> {
  await delay()
  return clone(getDb().notifications.filter((n) => n.audience.includes(role)))
}

export async function markNotificationRead(id: string): Promise<void> {
  await delay(120)
  commit((db) => {
    const notification = db.notifications.find((n) => n.id === id)
    if (notification) notification.read = true
  })
}

export async function markAllNotificationsRead(role: Role): Promise<void> {
  await delay(200)
  commit((db) => {
    db.notifications.forEach((n) => {
      if (n.audience.includes(role)) n.read = true
    })
  })
}

export async function listAuditLogs(): Promise<AuditLogEntry[]> {
  await delay()
  return clone(getDb().auditLogs)
}
