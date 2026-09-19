import type { User } from '@/types'
import { userFromDto, type UserDto } from './adapters/users'
import {
  apiRequest,
  clearAuthTokens,
  getRefreshToken,
  hasStoredSession,
  setAuthTokens,
} from './client'

interface LoginResponse {
  access: string
  refresh: string
}

interface EffectiveSettings {
  session_timeout_enabled: boolean
  session_timeout_minutes: number
}

export function getEffectiveSettings(): Promise<EffectiveSettings> {
  return apiRequest<EffectiveSettings>('/settings/effective/')
}

export async function getCurrentUser(): Promise<User> {
  return userFromDto(await apiRequest<UserDto>('/users/me/'))
}

export async function login(email: string, password: string): Promise<User> {
  const response = await apiRequest<LoginResponse>('/auth/login/', {
    method: 'POST',
    auth: false,
    body: { email: email.trim().toLowerCase(), password },
  })
  setAuthTokens({ access: response.access, refresh: response.refresh })
  try {
    return await getCurrentUser()
  } catch (error) {
    clearAuthTokens()
    throw error
  }
}

export async function logout(): Promise<void> {
  const refresh = getRefreshToken()
  try {
    if (refresh) await apiRequest<null>('/auth/logout/', { method: 'POST', body: { refresh } })
  } finally {
    clearAuthTokens()
  }
}

export async function restoreSession(): Promise<User | null> {
  if (!hasStoredSession()) return null
  try {
    return await getCurrentUser()
  } catch {
    clearAuthTokens()
    return null
  }
}

export async function updateCurrentUser(input: {
  fullName?: string
  phone?: string
  profileImage?: File
}): Promise<User> {
  let body: FormData | Record<string, unknown>
  if (input.profileImage) {
    const form = new FormData()
    if (input.fullName !== undefined) form.append('full_name', input.fullName)
    if (input.phone !== undefined) form.append('phone', input.phone)
    form.append('profile_image', input.profileImage)
    body = form
  } else {
    body = {
      ...(input.fullName !== undefined ? { full_name: input.fullName } : {}),
      ...(input.phone !== undefined ? { phone: input.phone } : {}),
    }
  }
  const dto = await apiRequest<UserDto>('/users/me/', {
    method: 'PATCH',
    body,
  })
  return userFromDto(dto)
}

export async function requestPasswordReset(email: string): Promise<void> {
  await apiRequest('/auth/password-reset/', {
    method: 'POST',
    auth: false,
    body: { email },
  })
}

/**
 * Local-development only: ask the backend to mint a password-reset link and
 * return it directly, so the flow needs no mailbox and sends no mail. The
 * endpoint answers 404 unless the server runs with DEBUG on, so this can never
 * work against production.
 */
export async function generateDevPasswordResetLink(email: string): Promise<string> {
  const result = await apiRequest<{ reset_url: string }>('/auth/dev/password-reset-link/', {
    method: 'POST',
    auth: false,
    body: { email },
  })
  return result.reset_url
}

export async function resetPassword(resetReference: string, newPassword: string): Promise<void> {
  const separator = resetReference.indexOf(':')
  const uid = separator >= 0 ? resetReference.slice(0, separator) : ''
  const token = separator >= 0 ? resetReference.slice(separator + 1) : resetReference
  await apiRequest('/auth/password-reset/confirm/', {
    method: 'POST',
    auth: false,
    body: { uid, token, new_password: newPassword, confirm_password: newPassword },
  })
}
