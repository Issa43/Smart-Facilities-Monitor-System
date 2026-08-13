import type { Role, User } from '@/types'
import { ApiError, delay, nowIso } from './client'
import { clone, commit, getDb } from './db'

/**
 * Mock authentication.
 *
 * DEMO ONLY — passwords are compared in plain text against the table below.
 * A real backend issues a token from POST /auth/login and this module becomes
 * a thin fetch wrapper; the function signatures below do not change.
 */

const SESSION_KEY = 'nozom.session.v1'

/** The four demo accounts, one per role. Documented in the README. */
const DEMO_PASSWORDS: Record<string, string> = {
  admin: 'Admin@1234',
  khalid: 'Build@1234',
  reem: 'Ops@1234',
  faisal: 'Guard@1234',
}

export interface DemoAccount {
  username: string
  password: string
  role: Role
  fullName: string
}

export const DEMO_ACCOUNTS: DemoAccount[] = [
  { username: 'admin', password: 'Admin@1234', role: 'super_admin', fullName: 'سارة العتيبي' },
  {
    username: 'khalid',
    password: 'Build@1234',
    role: 'construction_manager',
    fullName: 'خالد الشمري',
  },
  { username: 'reem', password: 'Ops@1234', role: 'operations_manager', fullName: 'ريم الدوسري' },
  { username: 'faisal', password: 'Guard@1234', role: 'security_officer', fullName: 'فيصل العنزي' },
]

export async function login(username: string, password: string): Promise<User> {
  await delay(500) // deliberately slower than a read — the submit button shows a spinner

  const normalized = username.trim().toLowerCase()
  const db = getDb()
  const user = db.users.find(
    (u) => u.username.toLowerCase() === normalized || u.email.toLowerCase() === normalized,
  )

  if (!user || DEMO_PASSWORDS[user.username] !== password) {
    throw new ApiError('اسم المستخدم أو كلمة المرور غير صحيحة', 401)
  }

  if (user.status === 'suspended') {
    throw new ApiError('هذا الحساب موقوف. يرجى التواصل مع المدير العام.', 403)
  }

  const stamped = commit((database) => {
    const record = database.users.find((u) => u.id === user.id)
    if (record) record.lastLoginAt = nowIso()
    return record ? clone(record) : clone(user)
  })

  localStorage.setItem(SESSION_KEY, stamped.id)
  return stamped
}

export function logout(): void {
  localStorage.removeItem(SESSION_KEY)
}

/**
 * Restores the signed-in user on page load. Synchronous on purpose: the router
 * needs to know whether to render the app or redirect before the first paint,
 * and an async check here would flash the login screen on every refresh.
 */
export function getStoredSession(): User | null {
  const id = localStorage.getItem(SESSION_KEY)
  if (!id) return null

  const user = getDb().users.find((u) => u.id === id)
  if (!user || user.status === 'suspended') {
    localStorage.removeItem(SESSION_KEY)
    return null
  }
  return clone(user)
}

/** Password reset — the request half. Always resolves, so the form cannot enumerate accounts. */
export async function requestPasswordReset(email: string): Promise<void> {
  await delay(600)
  void email
}

/** Password reset — the confirm half. */
export async function resetPassword(token: string, newPassword: string): Promise<void> {
  await delay(600)
  if (token === 'invalid') {
    throw new ApiError('رابط إعادة التعيين منتهي الصلاحية أو غير صالح', 400)
  }
  void newPassword
}
