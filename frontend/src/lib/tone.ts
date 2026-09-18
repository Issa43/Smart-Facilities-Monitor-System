import type { Tone } from '@/types'

/**
 * Canonical severity order for status distributions.
 *
 * This is not cosmetic. The chart palette's neutral grey is legible beside the
 * green success step (ΔE 15.8) but NOT beside the blue info step (ΔE 8.9 — a
 * hard fail for normal vision, before colour-vision deficiency). Emitting
 * slices in this order is what guarantees the two never end up adjacent.
 *
 * Lives in lib/ rather than in the chart layer so api/stats.ts can apply it
 * without the data layer importing from the component layer.
 */
export const TONE_ORDER: Record<Tone, number> = {
  critical: 0,
  warning: 1,
  info: 2,
  success: 3,
  neutral: 4,
}

export function sortByTone<T extends { tone: Tone }>(slices: T[]): T[] {
  return slices.slice().sort((a, b) => TONE_ORDER[a.tone] - TONE_ORDER[b.tone])
}

/**
 * Derives a tone from a percentage, so progress bars and rings colour
 * themselves consistently instead of each caller picking a threshold.
 */
export function progressTone(percent: number): Tone {
  if (percent >= 80) return 'success'
  if (percent >= 45) return 'info'
  if (percent >= 20) return 'warning'
  return 'critical'
}
