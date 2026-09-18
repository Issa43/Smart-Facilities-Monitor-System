import type { AccountStatus, Role, User } from '@/types'
import { API_BASE_URL, ApiError } from '../client'

export interface UserDto {
  id: string
  full_name: string
  email: string
  phone: string
  username: string
  role: string
  role_name: Role | null
  profile_image: string | null
  status: AccountStatus
  last_login: string | null
  created_at: string
  updated_at: string
}

export interface RoleDto {
  id: string
  name: Role
  name_display: string
  description: string
  created_at: string
  permissions: { id: string; permission_name: string }[]
}

export interface RoleRecord {
  id: string
  name: Role
  displayName: string
  description: string
  permissions: string[]
}

export function initialsOf(fullName: string): string {
  const parts = fullName.trim().split(/\s+/)
  return `${parts[0]?.[0] ?? '؟'}${parts[1]?.[0] ?? ''}`
}

function profileImageUrl(value: string | null): string | null {
  if (!value || /^https?:\/\//i.test(value)) return value
  try {
    return new URL(value, `${new URL(API_BASE_URL).origin}/`).toString()
  } catch {
    return value
  }
}

export function userFromDto(dto: UserDto): User {
  if (!dto.role_name) {
    throw new ApiError('This account has no assigned role.', 403, { role: ['A role is required.'] })
  }
  return {
    id: dto.id,
    fullName: dto.full_name,
    email: dto.email,
    phone: dto.phone,
    username: dto.username,
    role: dto.role_name,
    status: dto.status,
    profileImageUrl: profileImageUrl(dto.profile_image),
    initials: initialsOf(dto.full_name),
    lastLoginAt: dto.last_login,
    createdAt: dto.created_at,
    // Relationship counts are not in the current API contract. DELETE remains
    // authoritative and may reject users protected by domain references.
    // This relationship summary is not exposed by the current backend user DTO.
    hasOperationalRecords: null,
  }
}

export function roleFromDto(dto: RoleDto): RoleRecord {
  return {
    id: dto.id,
    name: dto.name,
    displayName: dto.name_display,
    description: dto.description,
    permissions: dto.permissions.map((permission) => permission.permission_name),
  }
}
