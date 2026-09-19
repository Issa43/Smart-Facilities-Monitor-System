import { ApiError } from '@/api/client'

export type SafetyErrorKind =
  | 'validation'
  | 'unauthenticated'
  | 'forbidden'
  | 'not_found'
  | 'conflict'
  | 'rate_limited'
  | 'unavailable'

export interface SafetyErrorPresentation {
  kind: SafetyErrorKind
  title: string
  description: string
  /** Whether the alert should be refetched to reconcile with the server. */
  reconcile: boolean
}

/**
 * Maps an API failure to a user-facing Arabic message. Backend exception text
 * is never shown; the server stays authoritative for every decision.
 */
export function presentSafetyError(error: unknown): SafetyErrorPresentation {
  const status = error instanceof ApiError ? error.status : 0
  if (status === 400) {
    return {
      kind: 'validation',
      title: 'تعذّر قبول البيانات المُدخلة',
      description: 'راجع الحقول المطلوبة ثم أعد المحاولة.',
      reconcile: false,
    }
  }
  if (status === 401) {
    return {
      kind: 'unauthenticated',
      title: 'انتهت الجلسة',
      description: 'سجّل الدخول مرة أخرى للمتابعة.',
      reconcile: false,
    }
  }
  if (status === 403) {
    return {
      kind: 'forbidden',
      title: 'لا تملك صلاحية هذا الإجراء',
      description: 'تحقق الخادم من صلاحياتك ونطاق مشاريعك ورفض الطلب.',
      reconcile: true,
    }
  }
  if (status === 404) {
    return {
      kind: 'not_found',
      title: 'الإنذار غير متاح',
      description: 'قد يكون الإنذار غير موجود أو خارج نطاق المشاريع المسندة إليك.',
      reconcile: true,
    }
  }
  if (status === 409) {
    return {
      kind: 'conflict',
      title: 'تعذّر تنفيذ الإجراء على حالة الإنذار الحالية',
      description:
        'ربما تغيّرت حالة الإنذار أو يتطلب القرار ملاحظات. تم تحديث البيانات من الخادم؛ راجعها ثم أعد المحاولة.',
      reconcile: true,
    }
  }
  if (status === 429) {
    return {
      kind: 'rate_limited',
      title: 'طلبات كثيرة خلال وقت قصير',
      description: 'انتظر قليلاً ثم أعد المحاولة.',
      reconcile: false,
    }
  }
  return {
    kind: 'unavailable',
    title: 'تعذّر الاتصال بخدمة السلامة',
    description: 'حدث خطأ في الخادم أو الشبكة. أعد المحاولة لاحقاً.',
    reconcile: false,
  }
}

/**
 * Provider-supplied source URLs are untrusted. Only https links on the approved
 * provider hosts become clickable; anything else is not linked at all.
 */
const SAFE_SOURCE_HOSTS = new Set(['earthquake.usgs.gov', 'www.gdacs.org', 'gdacs.org'])

export function safeSourceUrl(value: string): string | null {
  if (!value) return null
  try {
    const url = new URL(value)
    if (url.protocol !== 'https:' || url.username || url.password || url.port) return null
    return SAFE_SOURCE_HOSTS.has(url.hostname.toLowerCase()) ? url.toString() : null
  } catch {
    return null
  }
}
