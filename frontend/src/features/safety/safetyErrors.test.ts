import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/client'
import { presentSafetyError, safeSourceUrl } from './safetyErrors'

describe('safety error presentation', () => {
  it.each([
    [400, 'validation', false],
    [401, 'unauthenticated', false],
    [403, 'forbidden', true],
    [404, 'not_found', true],
    [409, 'conflict', true],
    [429, 'rate_limited', false],
    [500, 'unavailable', false],
    [0, 'unavailable', false],
  ] as const)('maps HTTP %s to %s', (status, kind, reconcile) => {
    const presentation = presentSafetyError(new ApiError('Traceback: internal detail', status))
    expect(presentation.kind).toBe(kind)
    expect(presentation.reconcile).toBe(reconcile)
    expect(`${presentation.title} ${presentation.description}`).not.toContain('Traceback')
  })

  it('treats non-API failures as unavailable without exposing their text', () => {
    const presentation = presentSafetyError(new TypeError('secret stack'))
    expect(presentation.kind).toBe('unavailable')
    expect(presentation.description).not.toContain('secret')
  })
})

describe('provider source URL safety', () => {
  it.each([
    'https://earthquake.usgs.gov/earthquakes/eventpage/us7000test',
    'https://www.gdacs.org/report.aspx?eventid=1&eventtype=FL',
    'https://gdacs.org/report',
  ])('links approved https provider pages: %s', (value) => {
    expect(safeSourceUrl(value)).toBe(new URL(value).toString())
  })

  it.each([
    '',
    'http://earthquake.usgs.gov/x',
    'https://evil.example/x',
    'https://earthquake.usgs.gov.evil.example/x',
    'https://user:pass@earthquake.usgs.gov/x',
    'https://earthquake.usgs.gov:8443/x',
    'javascript:alert(1)',
    'not a url',
  ])('refuses unsafe or unapproved URLs: %s', (value) => {
    expect(safeSourceUrl(value)).toBeNull()
  })
})
