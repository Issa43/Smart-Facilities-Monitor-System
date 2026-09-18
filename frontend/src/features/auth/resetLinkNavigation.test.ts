// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest'
import { followResetLink } from './resetLinkNavigation'

const UID = 'NjFhNGE5NGIt'
const TOKEN = 'df1t38-5c600e9d010cea67'

describe('followResetLink', () => {
  it('hands the backend URL to the router without rebuilding it', () => {
    const navigate = vi.fn()
    followResetLink(`http://localhost:3000/reset-password?uid=${UID}&token=${TOKEN}`, navigate)

    expect(navigate).toHaveBeenCalledWith(`/reset-password?uid=${UID}&token=${TOKEN}`, {
      replace: true,
    })
  })

  it('preserves query values verbatim, including characters that would re-encode', () => {
    const navigate = vi.fn()
    const token = 'abc-DEF_123.~xyz'
    followResetLink(`http://localhost:3000/reset-password?uid=${UID}&token=${token}`, navigate)

    const [path] = navigate.mock.calls[0]
    expect(path).toContain(`token=${token}`)
    expect(new URLSearchParams(path.split('?')[1]).get('token')).toBe(token)
  })

  it('replaces the history entry so Back does not return to the form', () => {
    const navigate = vi.fn()
    followResetLink(`http://localhost:3000/reset-password?uid=${UID}&token=${TOKEN}`, navigate)

    expect(navigate.mock.calls[0][1]).toEqual({ replace: true })
  })

  it('falls back to a full navigation when the link points at another origin', () => {
    const navigate = vi.fn()
    const assign = vi.fn()
    const original = window.location
    Object.defineProperty(window, 'location', {
      value: { ...original, origin: original.origin, assign },
      configurable: true,
    })

    const external = `http://localhost:5173/reset-password?uid=${UID}&token=${TOKEN}`
    followResetLink(external, navigate)

    expect(navigate).not.toHaveBeenCalled()
    expect(assign).toHaveBeenCalledWith(external)

    Object.defineProperty(window, 'location', { value: original, configurable: true })
  })
})
