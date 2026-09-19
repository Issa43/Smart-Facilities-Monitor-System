import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { canAccessRoleRoute } from '@/routes/routeAccess'
import { ROLE_ROUTES, navItemsFor } from '@/routes/routeConfig'
import type { HazardProvider, HazardType, Role } from '@/types'
import { HAZARD_PROVIDER_LABELS, HAZARD_TYPE_LABELS } from '@/types'

const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

const SAFETY_SOURCES = {
  api: source('../../api/safety.ts'),
  adapter: source('../../api/adapters/safety.ts'),
  types: source('../../types/safety.ts'),
  errors: source('./safetyErrors.ts'),
  list: source('./pages/SafetyAlertsPage.tsx'),
  detail: source('./pages/SafetyAlertDetailPage.tsx'),
}
const code = (text: string) => text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')

describe('safety frontend boundaries', () => {
  it('never uses `any` for Safety models or API code', () => {
    for (const [name, text] of Object.entries(SAFETY_SOURCES)) {
      expect(code(text), name).not.toMatch(/:\s*any\b|<any>|as any\b/)
    }
  })

  it('only talks to the SFLMS Safety API through the shared client', () => {
    const api = code(SAFETY_SOURCES.api)
    expect(api).not.toMatch(/https?:\/\//)
    expect(api).not.toMatch(/\bfetch\(|axios|XMLHttpRequest/)
    expect(api).not.toMatch(/ingest/)
    const paths = [...api.matchAll(/`(\/safety\/[^`]*)`|'(\/safety\/[^']*)'/g)].map(
      (match) => match[1] ?? match[2],
    )
    expect(new Set(paths)).toEqual(
      new Set([
        '/safety/alerts/',
        '/safety/alerts/${segment(id)}/',
        '/safety/alerts/${segment(id)}/${action}/',
        // Human decision workflow: propose on an alert, rule on a proposal.
        '/safety/alerts/${segment(alertId)}/proposals/',
        '/safety/action-proposals/',
        '/safety/action-proposals/${segment(id)}/',
        '/safety/action-proposals/${segment(id)}/${verdict}/',
        '/safety/hazard-events/',
        '/safety/hazard-events/${segment(id)}/',
        '/safety/monitoring-coverage/',
      ]),
    )
    for (const [name, text] of Object.entries(SAFETY_SOURCES)) {
      if (name === 'errors') continue
      expect(code(text), name).not.toMatch(
        /earthquake\.usgs\.gov|gdacs\.org|open-meteo|openweather/i,
      )
    }
  })

  it('does not model or render raw provider payloads, credentials, or realtime channels', () => {
    for (const [name, text] of Object.entries(SAFETY_SOURCES)) {
      const body = code(text)
      expect(body, name).not.toMatch(/\bpayload\b/)
      expect(body, name).not.toMatch(
        /WebSocket|EventSource|refetchInterval|setInterval|firebase|telegram/i,
      )
      expect(body, name).not.toMatch(
        /Authorization|Bearer|access_token|sessionStorage|localStorage/,
      )
    }
  })

  it('exposes Safety navigation to Construction, Operations, and Super Admin only', () => {
    const safetyPaths = (role: Role) =>
      navItemsFor(role)
        .map((item) => item.path)
        .filter((path) => path.includes('/safety-alerts'))
    expect(safetyPaths('construction_manager')).toEqual(['/construction/safety-alerts'])
    expect(safetyPaths('operations_manager')).toEqual(['/operations/safety-alerts'])
    expect(safetyPaths('super_admin')).toEqual(['/operations/safety-alerts'])
    expect(safetyPaths('security_officer')).toEqual([])
    expect(JSON.stringify(ROLE_ROUTES.security_officer)).not.toContain('safety-alerts')
  })

  it('places Safety routes inside the Construction and Operations protected branches', () => {
    const app = source('../../App.tsx')
    const branch = (role: string) => {
      const start = app.indexOf(`<ProtectedRoute role="${role}" />`)
      return app.slice(start, app.indexOf('</Route>', start))
    }
    expect(branch('construction_manager')).toContain('path="/construction/safety-alerts"')
    expect(branch('construction_manager')).toContain('path="/construction/safety-alerts/:alertId"')
    expect(branch('operations_manager')).toContain('path="/operations/safety-alerts"')
    expect(branch('operations_manager')).toContain('path="/operations/safety-alerts/:alertId"')
    expect(branch('security_officer')).not.toContain('safety-alerts')
    expect(canAccessRoleRoute('security_officer', 'operations_manager')).toBe(false)
    expect(canAccessRoleRoute('security_officer', 'construction_manager')).toBe(false)
    expect(canAccessRoleRoute('super_admin', 'operations_manager')).toBe(true)
  })
})

describe('safety taxonomy label coverage', () => {
  // Regression: `dust_storm` and `mhews` reached the API before the label maps
  // knew them, so the detail header rendered "undefined — <project>" and the
  // source column was blank.
  it('labels every hazard type the backend can send', () => {
    const hazardTypes: HazardType[] = [
      'earthquake',
      'tropical_cyclone',
      'flood',
      'volcano',
      'wildfire',
      'extreme_heat',
      'extreme_cold',
      'heavy_snow',
      'high_wind',
      'heavy_rain',
      'dust_storm',
    ]
    for (const hazardType of hazardTypes) {
      expect(HAZARD_TYPE_LABELS[hazardType]).toBeTruthy()
      expect(HAZARD_TYPE_LABELS[hazardType]).not.toBe(hazardType)
    }
  })

  it('labels every provider the backend can send', () => {
    const providers: HazardProvider[] = ['usgs', 'gdacs', 'mhews']
    for (const provider of providers) {
      expect(HAZARD_PROVIDER_LABELS[provider]).toBeTruthy()
    }
  })
})
