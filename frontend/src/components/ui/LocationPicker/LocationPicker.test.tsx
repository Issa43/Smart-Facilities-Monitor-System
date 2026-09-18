// @vitest-environment jsdom

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { LocationPicker } from './LocationPicker'

beforeAll(() => {
  // Leaflet measures its container; jsdom reports every box as 0x0, which
  // makes the map think it has no viewport.
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { value: 320, configurable: true })
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { value: 640, configurable: true })
  if (!('ResizeObserver' in globalThis)) {
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    )
  }
})

describe('LocationPicker', () => {
  it('renders the map with its instruction', () => {
    render(<LocationPicker value={null} onChange={vi.fn()} label="الموقع" hint="اضغط على الخريطة" />)

    expect(screen.getByTestId('location-picker-map')).toBeInTheDocument()
    expect(screen.getByText('اضغط على الخريطة')).toBeInTheDocument()
  })

  it('shows no coordinates until a point is chosen', () => {
    render(<LocationPicker value={null} onChange={vi.fn()} />)

    expect(screen.getByTestId('location-picker-readout')).toHaveTextContent('—')
  })

  it('shows the existing point when the project already has one', () => {
    render(<LocationPicker value={{ latitude: 34.8021, longitude: 38.9968 }} onChange={vi.fn()} />)

    expect(screen.getByTestId('location-picker-readout')).toHaveTextContent(
      '34.802100, 38.996800',
    )
  })

  it('is reachable as an application region for assistive tech', () => {
    render(<LocationPicker value={null} onChange={vi.fn()} label="الموقع الجغرافي" />)

    expect(screen.getByRole('application', { name: 'الموقع الجغرافي' })).toBeInTheDocument()
  })

  it('does not call onChange on its own', async () => {
    const onChange = vi.fn()
    render(<LocationPicker value={null} onChange={onChange} />)
    // Merely rendering the map, including its preview centre, must never
    // produce coordinates for the project.
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(onChange).not.toHaveBeenCalled()
  })

  it('reports a valid point when the map is clicked', async () => {
    const onChange = vi.fn()
    render(<LocationPicker value={null} onChange={onChange} />)

    screen
      .getByTestId('location-picker-map')
      .dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 320, clientY: 160 }))

    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1))
    const point = onChange.mock.calls[0][0]
    expect(point.latitude).toBeGreaterThanOrEqual(-90)
    expect(point.latitude).toBeLessThanOrEqual(90)
    // Leaflet reports wrapped longitudes past ±180 when the world repeats.
    expect(point.longitude).toBeGreaterThanOrEqual(-180)
    expect(point.longitude).toBeLessThanOrEqual(180)
  })

  it('leaves the container interactive unless disabled', async () => {
    const { rerender } = render(<LocationPicker value={null} onChange={vi.fn()} />)
    const map = screen.getByTestId('location-picker-map')
    expect(map.className).not.toMatch(/disabled/)

    rerender(<LocationPicker value={null} onChange={vi.fn()} disabled />)
    await userEvent.tab()
    expect(map.className).toMatch(/disabled/)
  })
})
