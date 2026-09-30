import { describe, expect, it } from 'vitest'
import { inDirection, toImagePoint } from './roiGeometry'

const frame = { width: 1280, height: 720 }

describe('toImagePoint', () => {
  it('maps a click on the scaled image back to camera pixels', () => {
    // Image shown at half size, offset on the page.
    const rect = { left: 100, top: 50, width: 640, height: 360 }
    expect(toImagePoint(420, 230, rect, frame)).toEqual({ x: 640, y: 360 })
  })

  it('clamps clicks that land just outside the image to its edge', () => {
    const rect = { left: 0, top: 0, width: 640, height: 360 }
    expect(toImagePoint(-5, 400, rect, frame)).toEqual({ x: 0, y: 720 })
  })
})

describe('inDirection', () => {
  it('points below a line drawn left to right, like the ANPR detector', () => {
    expect(inDirection({ x: 0, y: 500 }, { x: 1000, y: 500 })).toEqual({ x: -0, y: 1 })
  })

  it('flips when the line is drawn the other way', () => {
    expect(inDirection({ x: 1000, y: 500 }, { x: 0, y: 500 })).toEqual({ x: -0, y: -1 })
  })
})
