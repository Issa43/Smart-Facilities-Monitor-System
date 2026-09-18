/**
 * Fixture dates are generated relative to the moment the database is seeded,
 * not hard-coded. A demo run in 2027 looks exactly as current as one in 2026 —
 * "last updated 3 days ago" stays true instead of drifting into the past.
 */

const DAY = 86_400_000

export function daysAgo(n: number, hour = 10, minute = 0): string {
  const d = new Date(Date.now() - n * DAY)
  d.setHours(hour, minute, 0, 0)
  return d.toISOString()
}

export function daysAhead(n: number, hour = 10, minute = 0): string {
  return daysAgo(-n, hour, minute)
}

export function hoursAgo(n: number): string {
  return new Date(Date.now() - n * 3_600_000).toISOString()
}

export function minutesAgo(n: number): string {
  return new Date(Date.now() - n * 60_000).toISOString()
}

/** Gradients stand in for uploaded photos — keeps the repo free of binary assets. */
export const GRADIENTS = [
  'linear-gradient(135deg, #DDF3FF, #B8E4FA)',
  'linear-gradient(135deg, #F3E8FF, #DDF3FF)',
  'linear-gradient(135deg, #E4FBF2, #DDF3FF)',
  'linear-gradient(135deg, #FEF6E0, #F3E8FF)',
  'linear-gradient(135deg, #E8FBFE, #E4FBF2)',
  'linear-gradient(135deg, #DDF3FF, #F3E8FF)',
] as const

export function gradient(index: number): string {
  return GRADIENTS[index % GRADIENTS.length] as string
}
