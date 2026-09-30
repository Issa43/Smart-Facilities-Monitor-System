import type { PixelPoint } from '@/types'

export type Size = { width: number; height: number }
type Rect = { left: number; top: number; width: number; height: number }

/**
 * A click on the displayed image, in the camera's own pixel coordinates.
 *
 * The image is scaled to fit the page, but detectors test ROIs against the
 * full-resolution frame, so the click is mapped back to that resolution and
 * clamped to the frame.
 */
export function toImagePoint(clientX: number, clientY: number, rect: Rect, size: Size): PixelPoint {
  const clamp = (value: number, max: number) => Math.min(Math.max(value, 0), max)
  return {
    x: Math.round(clamp(((clientX - rect.left) * size.width) / rect.width, size.width)),
    y: Math.round(clamp(((clientY - rect.top) * size.height) / rect.height, size.height)),
  }
}

/**
 * Unit vector pointing to the side of the line start -> end that the ANPR
 * detector counts as IN (entry).
 *
 * The detector (direction.side_of_line) calls the side where the cross product
 * is positive IN, and the normal (-dy, dx) points there: below a line drawn
 * left to right. Drawing this arrow lets the admin see which way is entry.
 */
export function inDirection(start: PixelPoint, end: PixelPoint): PixelPoint {
  const dx = end.x - start.x
  const dy = end.y - start.y
  const length = Math.max(Math.hypot(dx, dy), 1e-6)
  return { x: -dy / length, y: dx / length }
}
