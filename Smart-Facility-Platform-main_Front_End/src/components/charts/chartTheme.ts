import type { Tone } from '@/types'

/**
 * Chart colour system.
 *
 * WHY THESE ARE NOT THE BADGE COLOURS
 * The soft token tints (--success #34D399, --warning #FBBF24, …) are correct for
 * badge fills behind dark text, but as chart marks on white they fail on every
 * count: all sit above the L 0.77 lightness band, all fall under 3:1 contrast
 * against the surface, and neighbouring pairs collapse to ΔE ~12 for normal
 * vision — unreadable, before colour-vision deficiency is even considered.
 *
 * These are deeper steps from the same hue families, verified with the dataviz
 * palette validator:
 *
 *   Lightness band       PASS  all inside L 0.43–0.77
 *   Chroma floor         PASS  all >= 0.1
 *   CVD separation       PASS  worst adjacent ΔE 8.8 (protan)
 *   Normal-vision floor  PASS  worst adjacent ΔE 16.6
 *   Contrast vs surface  PASS  all >= 3:1
 *
 * RULES THAT KEEP IT VALID — do not break these when adding a chart:
 *  1. Assign SERIES in fixed order. Never cycle a 7th colour; fold the tail into
 *     "أخرى" or use small multiples.
 *  2. Status slices emit in severity order (critical → warning → info → success →
 *     neutral). The neutral grey is legible beside green but NOT beside blue
 *     (ΔE 8.9, a hard fail), and that ordering is the only thing preventing it.
 *  3. Never a second Y axis. Two measures of different scale get two charts.
 */

/** Fixed-order categorical palette. Validated for CVD; assign by index, never cycle. */
export const CHART_SERIES = [
  '#0A6FA8', // brand blue
  '#7C3AED', // brand purple
  '#0E9F6E', // green
  '#D97706', // amber
  '#E11D48', // rose
  '#0891B2', // cyan
] as const

/** Status colours — reserved for state, never reused as "series 4". */
export const STATUS_COLORS: Record<Tone, string> = {
  critical: '#E11D48',
  warning: '#D97706',
  info: '#0A6FA8',
  success: '#0E9F6E',
  neutral: '#64748B',
}

/** Severity order lives in lib/tone.ts — api/stats.ts applies it when building slices. */
export { TONE_ORDER, sortByTone } from '@/lib/tone'

export function seriesColor(index: number): string {
  return CHART_SERIES[index] ?? STATUS_COLORS.neutral
}

/* ==========================================================================
   Shared Recharts props — RTL configured once, here
   ========================================================================== */

export const AXIS_STYLE = {
  fontSize: 11,
  fontFamily: 'var(--font-body)',
  fill: 'var(--text-faint)',
} as const

/**
 * Category axis. `reversed` is the RTL-critical bit: without it the earliest
 * month renders on the left and an Arabic reader scans the series backwards.
 */
export const X_AXIS_PROPS = {
  reversed: true,
  tickLine: false,
  axisLine: false,
  tick: AXIS_STYLE,
  dy: 6,
} as const

/** Value axis on the right — the side an RTL reader starts from. */
export const Y_AXIS_PROPS = {
  orientation: 'right',
  tickLine: false,
  axisLine: false,
  tick: AXIS_STYLE,
  width: 42,
} as const

/** Recessive gridlines: horizontal only, so they read as a scale, not a cage. */
export const GRID_PROPS = {
  stroke: 'var(--border)',
  strokeDasharray: '3 3',
  vertical: false,
} as const

export const CHART_MARGIN = { top: 8, right: 4, bottom: 0, left: 4 } as const
