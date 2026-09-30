// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RoiDrawer } from './RoiDrawer'

function loadImage(width: number, height: number) {
  const image = screen.getByAltText('صورة الكاميرا الحالية') as HTMLImageElement
  Object.defineProperty(image, 'naturalWidth', { value: width })
  Object.defineProperty(image, 'naturalHeight', { value: height })
  fireEvent.load(image)
}

describe('RoiDrawer', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ json: async () => ({ camera_id: 'camera-1' }) })),
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  it('adds a point in camera pixels for each click on the image', () => {
    const onChange = vi.fn()
    render(<RoiDrawer cameraId="camera-1" existing={[]} points={[]} onChange={onChange} />)
    loadImage(1280, 720)

    const canvas = screen.getByRole('img', { name: 'ارسم منطقة ROI بالنقر على الصورة' })
    canvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 640, height: 360 }) as DOMRect
    fireEvent.click(canvas, { clientX: 320, clientY: 90 })

    expect(onChange).toHaveBeenCalledWith([{ x: 640, y: 180 }])
  })

  it('warns when the running detector watches a different camera', async () => {
    render(<RoiDrawer cameraId="camera-2" existing={[]} points={[]} onChange={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('الصورة من كاميرا أخرى')).toBeTruthy())
  })

  it('draws a line from two clicks, and a third click starts a new line', () => {
    const onChange = vi.fn()
    const line = [
      { x: 0, y: 500 },
      { x: 1000, y: 500 },
    ]
    render(
      <RoiDrawer mode="line" cameraId="camera-1" existing={[]} points={line} onChange={onChange} />,
    )
    loadImage(1280, 720)

    const canvas = screen.getByRole('img', { name: 'ارسم الخط الافتراضي بالنقر على الصورة' })
    canvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 640, height: 360 }) as DOMRect
    fireEvent.click(canvas, { clientX: 100, clientY: 50 })

    expect(onChange).toHaveBeenCalledWith([{ x: 200, y: 100 }])
    expect(screen.getByText('IN')).toBeTruthy()
    expect(screen.getByText('الخط جاهز للحفظ — السهم يشير إلى جهة الدخول')).toBeTruthy()
  })

  it('draws on the frame of the detector it is given', () => {
    render(
      <RoiDrawer
        mode="line"
        streamUrl="http://localhost:8092/stream"
        cameraId="camera-1"
        existing={[]}
        points={[]}
        onChange={vi.fn()}
      />,
    )

    const image = screen.getByAltText('صورة الكاميرا الحالية') as HTMLImageElement
    expect(image.src).toContain('http://localhost:8092/snapshot/raw')
    expect(fetch).toHaveBeenCalledWith('http://localhost:8092/info')
  })

  it('explains how to recover when the detector is not running', () => {
    render(<RoiDrawer cameraId="camera-1" existing={[]} points={[]} onChange={vi.fn()} />)
    fireEvent.error(screen.getByAltText('صورة الكاميرا الحالية'))

    expect(screen.getByText('تعذّر تحميل صورة الكاميرا')).toBeTruthy()
  })
})
