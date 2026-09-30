import { formatNumber } from '@/lib/format'

/** Mirrors the backend limit in apps.security.services.MAX_REQUIRED_CAMERA_COUNT. */
export const MAX_REQUIRED_CAMERA_COUNT = 200

/** Returns an Arabic validation message, or null when the value is acceptable. */
export function validateRequiredCameraCount(value: string): string | null {
  if (!value.trim()) return 'أدخل عدد الكاميرات المطلوب.'
  if (!/^\d+$/.test(value.trim())) return 'يجب أن يكون العدد رقماً صحيحاً غير سالب.'
  if (Number(value) > MAX_REQUIRED_CAMERA_COUNT) {
    return `الحد الأعلى ${formatNumber(MAX_REQUIRED_CAMERA_COUNT)} كاميرا.`
  }
  return null
}
