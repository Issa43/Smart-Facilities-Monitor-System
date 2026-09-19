/**
 * Formatting helpers.
 *
 * Locale: `ar-SA-u-ca-gregory-nu-latn`
 *   ar-SA        Arabic month and weekday names
 *   ca-gregory   Gregorian calendar (the default for ar-SA would be Hijri)
 *   nu-latn      Western digits (the default for ar-SA would be Arabic-Indic)
 *
 * That combination — Arabic words, Gregorian dates, Western numerals — is what
 * Saudi engineering and business dashboards use, and it keeps figures readable
 * in dense tables and on chart axes.
 *
 * Intl does everything needed here, so the project carries no date library.
 */

const LOCALE = 'ar-SA-u-ca-gregory-nu-latn'

/* Formatters are created once — constructing an Intl formatter is expensive. */
const dateLong = new Intl.DateTimeFormat(LOCALE, {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
})
const dateShort = new Intl.DateTimeFormat(LOCALE, {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
})
const dayMonth = new Intl.DateTimeFormat(LOCALE, { day: 'numeric', month: 'short' })
const timeOnly = new Intl.DateTimeFormat(LOCALE, {
  hour: '2-digit',
  minute: '2-digit',
  hour12: true,
})
const weekdayLong = new Intl.DateTimeFormat(LOCALE, { weekday: 'long' })
const monthLong = new Intl.DateTimeFormat(LOCALE, { month: 'long' })
const number = new Intl.NumberFormat(LOCALE)
const decimal1 = new Intl.NumberFormat(LOCALE, {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

function toDate(value: string | Date): Date | null {
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

/** "15 مارس 2026" */
export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const date = toDate(value)
  return date ? dateLong.format(date) : '—'
}

/** "15/03/2026" — for dense tables where the long form would wrap. */
export function formatDateShort(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const date = toDate(value)
  return date ? dateShort.format(date) : '—'
}

/** "15 مارس" — for chart axes and timelines. */
export function formatDayMonth(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const date = toDate(value)
  return date ? dayMonth.format(date) : '—'
}

/** "02:30 م" */
export function formatTime(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const date = toDate(value)
  return date ? timeOnly.format(date) : '—'
}

/** "15 مارس 2026 — 02:30 م" */
export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const date = toDate(value)
  return date ? `${dateLong.format(date)} — ${timeOnly.format(date)}` : '—'
}

/** "الأحد" */
export function formatWeekday(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const date = toDate(value)
  return date ? weekdayLong.format(date) : '—'
}

/** "مارس" */
export function formatMonth(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const date = toDate(value)
  return date ? monthLong.format(date) : '—'
}

/** "1,234,567" */
export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return number.format(value)
}

/** "12.5" */
export function formatDecimal(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return decimal1.format(value)
}

/**
 * "68%" — takes a whole number (68), not a fraction (0.68).
 * Uses the ASCII "%" rather than Intl's Arabic "٪" to match the Western digits.
 */
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${number.format(value)}%`
}

/** "1.2 ميجابايت" / "840 كيلوبايت" */
export function formatFileSize(kb: number): string {
  return kb >= 1024 ? `${decimal1.format(kb / 1024)} ميجابايت` : `${number.format(kb)} كيلوبايت`
}

/** "منذ 3 ساعات" — relative time, for activity feeds and notification rows. */
export function formatRelative(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const date = toDate(value)
  if (!date) return '—'

  const seconds = Math.round((Date.now() - date.getTime()) / 1000)
  if (seconds < 60) return 'الآن'

  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return minutes === 1 ? 'منذ دقيقة' : `منذ ${number.format(minutes)} دقيقة`

  const hours = Math.round(minutes / 60)
  if (hours < 24) return hours === 1 ? 'منذ ساعة' : `منذ ${number.format(hours)} ساعة`

  const days = Math.round(hours / 24)
  if (days < 30) return days === 1 ? 'أمس' : `منذ ${number.format(days)} يوم`

  return dateLong.format(date)
}

/** Whole days between two dates — negative when the target is in the past. */
export function daysUntil(value: string | Date): number {
  const date = toDate(value)
  if (!date) return 0
  return Math.ceil((date.getTime() - Date.now()) / 86_400_000)
}
