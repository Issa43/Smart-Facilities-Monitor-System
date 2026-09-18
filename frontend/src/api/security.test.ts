// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest'

const response = (body: unknown, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

afterEach(async () => {
  const { clearAuthTokens } = await import('./client')
  clearAuthTokens()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('security workflow contracts', () => {
  it('lists incident summaries without per-record action, evidence, or note requests', async () => {
    const incident = {
      id: 'incident-1',
      incident_number: 'INC-2026-0001',
      facility_id: 'facility-1',
      facility_name: 'Main Facility',
      alert_id: null,
      incident_type: 'water_leak',
      description: 'Pipe rupture',
      location: 'Plant room',
      severity_level: 'high',
      assigned_to_id: null,
      status: 'open',
      final_report: null,
      closed_by_id: null,
      closed_at: null,
      created_by_id: 'security-1',
      created_at: '2026-08-23T10:00:00Z',
      updated_at: '2026-08-23T10:00:00Z',
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValue(response({ count: 1, next: null, previous: null, results: [incident] }))
    vi.stubGlobal('fetch', fetchMock)
    const { listIncidents } = await import('./security')

    const incidents = await listIncidents()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(incidents[0]).toMatchObject({ id: 'incident-1', actions: [], evidence: [], notes: [] })
  })

  it('uses authenticated protected document downloads and canonical deletion', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response('protected', {
          status: 200,
          headers: { 'Content-Type': 'application/pdf' },
        }),
      )
      .mockResolvedValueOnce(response(null, 204))
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:safety-document')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const { setAuthTokens } = await import('./client')
    const { deleteSafetyDocument, downloadSafetyDocument } = await import('./security')
    setAuthTokens({ access: 'access-1', refresh: 'refresh-1' })

    await downloadSafetyDocument('document-1', 'policy.pdf')
    await deleteSafetyDocument('document-1')

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      '/security/documents/document-1/download/',
    )
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('Authorization')).toBe(
      'Bearer access-1',
    )
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/security/documents/document-1/')
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe('DELETE')
  })

  it('transfers to the explicitly selected operations manager', async () => {
    const incident = {
      id: 'incident-1',
      incident_number: 'INC-2026-0001',
      facility_id: 'facility-1',
      facility_name: 'Main Facility',
      alert_id: null,
      incident_type: 'water_leak',
      description: 'Pipe rupture',
      location: 'Plant room',
      severity_level: 'high',
      assigned_to_id: 'ops-2',
      status: 'transferred',
      final_report: null,
      closed_by_id: null,
      closed_at: null,
      created_by_id: 'security-1',
      created_at: '2026-08-23T10:00:00Z',
      updated_at: '2026-08-23T11:00:00Z',
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(incident))
      .mockImplementation(() =>
        Promise.resolve(response({ count: 0, next: null, previous: null, results: [] })),
      )
    vi.stubGlobal('fetch', fetchMock)
    const { escalateToOperations } = await import('./security')

    await escalateToOperations('incident-1', 'ops-2')

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      '/security/incidents/incident-1/transfer/',
    )
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      assigned_to: 'ops-2',
    })
  })
})
