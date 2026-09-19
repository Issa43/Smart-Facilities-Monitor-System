import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

describe('preserved route inventory', () => {
  it('retains all 71 application routes', () => {
    const source = readFileSync(new URL('../App.tsx', import.meta.url), 'utf8')
    const paths = [...source.matchAll(/path="([^"]+)"/g)].map((match) => match[1])

    expect(paths).toHaveLength(71)
    expect(new Set(paths).size).toBe(71)
    expect(paths).toEqual(
      expect.arrayContaining([
        '/admin/dashboard',
        '/admin/material-requests',
        '/admin/ai-camera-configuration',
        '/construction/dashboard',
        '/construction/reports',
        '/operations/dashboard',
        '/security/dashboard',
        '/security/events',
        '/security/events/:eventId',
        '/construction/safety-alerts',
        '/construction/safety-alerts/:alertId',
        '/operations/safety-alerts',
        '/operations/safety-alerts/:alertId',
        '/profile',
        '/help',
        // Local-development shortcut; see the DEV-gating assertion below.
        '/dev/password-reset',
      ]),
    )
  })

  it('keeps the development-only route out of production builds', () => {
    const source = readFileSync(new URL('../App.tsx', import.meta.url), 'utf8')
    const lines = source.split(/\r?\n/)
    const devRouteLine = lines.findIndex((line) =>
      line.includes('path="/dev/password-reset"'),
    )

    expect(devRouteLine).toBeGreaterThan(-1)
    // The route must sit inside an `import.meta.env.DEV` guard so the bundler
    // drops it from a production build.
    const preceding = lines.slice(Math.max(0, devRouteLine - 4), devRouteLine).join('\n')
    expect(preceding).toContain('import.meta.env.DEV')
  })
})
