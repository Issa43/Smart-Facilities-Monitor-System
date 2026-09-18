import type { AccountStatus, AppNotification, AuditLogEntry, Role, User } from '@/types'
import {
  roleFromDto,
  userFromDto,
  type RoleDto,
  type RoleRecord,
  type UserDto,
} from './adapters/users'
import { apiRequest, fetchAllPages, type PaginatedResponse } from './client'

export interface UserInput {
  fullName: string
  email: string
  phone: string
  username: string
  role: Role
  status: User['status']
  password?: string
  profileImage?: File | null
}

let rolesCache: RoleRecord[] | null = null

export async function listRoles(): Promise<RoleRecord[]> {
  if (rolesCache) return rolesCache
  rolesCache = (await fetchAllPages<RoleDto>('/users/roles/')).map(roleFromDto)
  return rolesCache
}

export async function updateRolePermissions(
  role: Role,
  permissions: string[],
): Promise<RoleRecord> {
  const record = (await listRoles()).find((candidate) => candidate.name === role)
  if (!record) throw new Error(`Role ${role} was not found.`)
  const updated = roleFromDto(
    await apiRequest<RoleDto>(`/users/roles/${record.id}/permissions/`, {
      method: 'PUT',
      body: { permissions },
    }),
  )
  rolesCache = (rolesCache ?? []).map((candidate) =>
    candidate.id === updated.id ? updated : candidate,
  )
  return updated
}

async function roleId(role: Role): Promise<string> {
  const record = (await listRoles()).find((candidate) => candidate.name === role)
  if (!record) throw new Error(`Role ${role} was not found.`)
  return record.id
}

export async function listUsers(): Promise<User[]> {
  return (await fetchAllPages<UserDto>('/users/')).map(userFromDto)
}

export interface UserPage {
  items: User[]
  count: number
  page: number
  pageSize: number
  totalPages: number
}

export type UserOrdering = '-created_at' | 'created_at' | 'full_name' | '-full_name'

export async function listUsersPage(options: {
  page: number
  search?: string
  role?: Role
  status?: AccountStatus
  ordering?: UserOrdering
}): Promise<UserPage> {
  const params = new URLSearchParams({
    page: String(options.page),
    ordering: options.ordering ?? '-created_at',
  })
  if (options.search?.trim()) params.set('search', options.search.trim())
  if (options.role) params.set('role', await roleId(options.role))
  if (options.status) params.set('status', options.status)
  const result = await apiRequest<PaginatedResponse<UserDto>>(`/users/?${params.toString()}`)
  return {
    items: result.results.map(userFromDto),
    count: result.count,
    page: result.current_page,
    pageSize: result.page_size,
    totalPages: result.total_pages,
  }
}

export async function getUser(id: string): Promise<User> {
  return userFromDto(await apiRequest<UserDto>(`/users/${id}/`))
}

export async function createUser(input: UserInput): Promise<User> {
  if (!input.password) throw new Error('A password is required.')
  return userFromDto(
    await apiRequest<UserDto>('/users/', {
      method: 'POST',
      body: {
        full_name: input.fullName,
        email: input.email,
        phone: input.phone,
        username: input.username,
        role: await roleId(input.role),
        status: input.status,
        password: input.password,
        confirm_password: input.password,
      },
    }),
  )
}

export async function updateUser(id: string, input: Partial<UserInput>): Promise<User> {
  const role = input.role === undefined ? undefined : await roleId(input.role)
  if (input.profileImage) {
    const body = new FormData()
    if (input.fullName !== undefined) body.set('full_name', input.fullName)
    if (input.phone !== undefined) body.set('phone', input.phone)
    if (role !== undefined) body.set('role', role)
    if (input.status !== undefined) body.set('status', input.status)
    body.set('profile_image', input.profileImage)
    return userFromDto(
      await apiRequest<UserDto>(`/users/${id}/`, {
        method: 'PATCH',
        body,
      }),
    )
  }
  return userFromDto(
    await apiRequest<UserDto>(`/users/${id}/`, {
      method: 'PATCH',
      body: {
        ...(input.fullName !== undefined ? { full_name: input.fullName } : {}),
        ...(input.phone !== undefined ? { phone: input.phone } : {}),
        ...(role !== undefined ? { role } : {}),
        ...(input.status !== undefined ? { status: input.status } : {}),
      },
    }),
  )
}

export async function deleteUser(id: string): Promise<void> {
  await apiRequest(`/users/${id}/`, { method: 'DELETE' })
}

export function setUserStatus(id: string, status: User['status']): Promise<User> {
  return updateUser(id, { status })
}

export async function resetUserPassword(id: string): Promise<void> {
  const user = await getUser(id)
  await apiRequest('/auth/password-reset/', {
    method: 'POST',
    auth: false,
    body: { email: user.email },
  })
}

interface NotificationDto {
  id: string
  title: string
  body: string
  category: AppNotification['category']
  tone: AppNotification['tone']
  read: boolean
  audience: Role[]
  href: string | null
  created_at: string
}

const notificationFromDto = (dto: NotificationDto): AppNotification => ({
  id: dto.id,
  title: dto.title,
  body: dto.body,
  category: dto.category,
  tone: dto.tone,
  read: dto.read,
  audience: dto.audience,
  href: dto.href,
  createdAt: dto.created_at,
})

export async function listNotifications(_role: Role): Promise<AppNotification[]> {
  return (await fetchAllPages<NotificationDto>('/notifications/')).map(notificationFromDto)
}

export async function markNotificationRead(id: string): Promise<void> {
  await apiRequest(`/notifications/${id}/read/`, { method: 'POST' })
}

export async function markAllNotificationsRead(_role: Role): Promise<void> {
  await apiRequest('/notifications/read-all/', { method: 'POST' })
}

interface AuditDto {
  id: string | number
  actor_id: string | null
  actor_name: string | null
  action: string
  entity: string
  entity_ref: string
  ip: string | null
  created_at: string
}

const auditFromDto = (dto: AuditDto): AuditLogEntry => ({
  id: String(dto.id),
  actorId: dto.actor_id ?? '',
  actorName: dto.actor_name ?? 'مستخدم محذوف',
  action: dto.action,
  entity: dto.entity,
  entityRef: dto.entity_ref,
  ip: dto.ip ?? '',
  createdAt: dto.created_at,
})

export async function listAuditLogs(): Promise<AuditLogEntry[]> {
  return (await fetchAllPages<AuditDto>('/audit-logs/')).map(auditFromDto)
}

export interface AuditLogPage {
  items: AuditLogEntry[]
  count: number
  page: number
  totalPages: number
}

export async function listAuditLogsPage(options: {
  page: number
  search?: string
  entity?: string
}): Promise<AuditLogPage> {
  const params = new URLSearchParams({ page: String(options.page), ordering: '-created_at' })
  if (options.search?.trim()) params.set('search', options.search.trim())
  if (options.entity && options.entity !== 'all') params.set('entity_type', options.entity)
  const result = await apiRequest<PaginatedResponse<AuditDto>>(`/audit-logs/?${params.toString()}`)
  return {
    items: result.results.map(auditFromDto),
    count: result.count,
    page: result.current_page,
    totalPages: result.total_pages,
  }
}

export async function listMyAuditLogs(): Promise<AuditLogEntry[]> {
  return (await fetchAllPages<AuditDto>('/audit-logs/mine/')).map(auditFromDto)
}
