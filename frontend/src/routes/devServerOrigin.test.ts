import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

/**
 * The backend only sends `Access-Control-Allow-Origin` for the dev origins it
 * is configured with (localhost:5173 among them). Vite's default behaviour when
 * 5173 is busy is to start on the next free port instead, which moves the app
 * to an origin the API rejects: the page still loads, because Vite serves it
 * same-origin, but every API call fails its preflight and the UI looks broken
 * for no visible reason. Pinning the port turns that into a startup error that
 * names the conflict.
 */
describe('dev server origin', () => {
  const config = readFileSync(new URL('../../vite.config.ts', import.meta.url), 'utf8')

  it('pins the dev server to the origin the backend allows', () => {
    expect(config).toMatch(/port:\s*5173/)
  })

  it('refuses to drift to another port rather than failing CORS silently', () => {
    expect(config).toMatch(/strictPort:\s*true/)
  })
})
