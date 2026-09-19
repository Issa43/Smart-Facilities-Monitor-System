import { apiRequest, fetchAllPages } from './client'

export interface SystemSetting {
  id: string
  key: string
  value: unknown
  description: string
  version: number
  updated_at: string
}

export function listSystemSettings(): Promise<SystemSetting[]> {
  return fetchAllPages<SystemSetting>('/settings/?ordering=key')
}

export function updateSystemSetting(
  setting: SystemSetting,
  value: unknown,
): Promise<SystemSetting> {
  return apiRequest<SystemSetting>(`/settings/${encodeURIComponent(setting.key)}/`, {
    method: 'PATCH',
    body: { value, version: setting.version },
  })
}
