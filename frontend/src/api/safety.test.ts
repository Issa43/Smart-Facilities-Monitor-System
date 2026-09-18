// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest'
import { alertDto } from '@/test/safetyFixtures'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const page = (results: unknown[]) => ({
  count: results.length,
  total_pages: 1,
  current_page: 1,
  page_size: 20,
  next: null,
  previous: null,
  results,
})

async function setup(...responses: Response[]) {
  const fetchMock = vi.fn()
  responses.forEach((response) => fetchMock.mockResolvedValueOnce(response))
  vi.stubGlobal('fetch', fetchMock)
  const client = await import('./client')
  client.setAuthTokens({ access: 'access-token', refresh: 'refresh-token' })
  const safety = await import('./safety')
  return { fetchMock, safety, client }
}

const url = (fetchMock: ReturnType<typeof vi.fn>, index = 0) =>
  new URL(String(fetchMock.mock.calls[index]?.[0]))
const init = (fetchMock: ReturnType<typeof vi.fn>, index = 0) =>
  fetchMock.mock.calls[index]?.[1] as RequestInit

afterEach(async () => {
  const { clearAuthTokens } = await import('./client')
  clearAuthTokens()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('safety API client', () => {
  it('lists alerts with only the Phase 3 filter names and maps the DTO', async () => {
    const { fetchMock, safety } = await setup(json(page([alertDto()])))

    const result = await safety.listSafetyAlerts({
      page: 2,
      project: '22222222-2222-4222-8222-222222222222',
      severity: 'critical',
      status: 'new',
      hazardType: 'flood',
      provider: 'gdacs',
      hazardWithdrawn: false,
      createdAfter: '2026-09-01T00:00:00.000Z',
      createdBefore: '2026-09-30T23:59:59.999Z',
      search: '  Cairo  ',
      ordering: '-distance_km',
    })

    const requested = url(fetchMock)
    expect(requested.pathname).toBe('/api/v1/safety/alerts/')
    expect(Object.fromEntries(requested.searchParams)).toEqual({
      page: '2',
      project: '22222222-2222-4222-8222-222222222222',
      severity: 'critical',
      status: 'new',
      hazard_type: 'flood',
      provider: 'gdacs',
      hazard_withdrawn: 'false',
      created_after: '2026-09-01T00:00:00.000Z',
      created_before: '2026-09-30T23:59:59.999Z',
      search: 'Cairo',
      ordering: '-distance_km',
    })
    expect(init(fetchMock).method).toBeUndefined()
    expect(new Headers(init(fetchMock).headers).get('Authorization')).toBe('Bearer access-token')
    expect(result).toMatchObject({ count: 1, page: 1, totalPages: 1 })
    expect(result.items[0]).toMatchObject({
      id: '11111111-1111-4111-8111-111111111111',
      distanceKm: '33.00',
      recommendedAction: 'suspend_outdoor_work',
      availableActions: ['acknowledge', 'dismiss'],
      project: { name: 'Cairo construction', facilityId: null },
      hazardEvent: { providerEventId: 'us7000test', providerUpdatedAt: '2026-09-15T12:05:00Z' },
    })
  })

  it('omits empty filters and the first page', async () => {
    const { fetchMock, safety } = await setup(json(page([])))
    await safety.listSafetyAlerts({ page: 1, search: '   ' })
    expect(url(fetchMock).search).toBe('')
  })

  it('ignores unknown available actions from the server', async () => {
    const { safety } = await setup(
      json(alertDto({ available_actions: ['acknowledge', 'evacuate', 'delete'] })),
    )
    const alert = await safety.getSafetyAlert('11111111-1111-4111-8111-111111111111')
    expect(alert.availableActions).toEqual(['acknowledge'])
  })

  it('posts workflow actions with exact bodies and no server-owned fields', async () => {
    const updated = json(alertDto({ status: 'acknowledged' }))
    const { fetchMock, safety } = await setup(
      updated,
      json(alertDto()),
      json(alertDto()),
      json(alertDto()),
      json(alertDto()),
      json(alertDto()),
    )
    const id = '11111111-1111-4111-8111-111111111111'

    await safety.acknowledgeSafetyAlert(id)
    await safety.decideSafetyAlert(id, { decision: 'other', notes: '  Delay pour  ' })
    await safety.decideSafetyAlert(id, { decision: 'monitor', notes: '   ' })
    await safety.dismissSafetyAlert(id, '  Not relevant  ')
    await safety.closeSafetyAlert(id, '')
    await safety.closeSafetyAlert(id, ' Done ')

    const calls = fetchMock.mock.calls.map(([target, request]) => ({
      path: new URL(String(target)).pathname,
      method: (request as RequestInit).method,
      body: JSON.parse(String((request as RequestInit).body)),
    }))
    expect(calls).toEqual([
      { path: `/api/v1/safety/alerts/${id}/acknowledge/`, method: 'POST', body: {} },
      {
        path: `/api/v1/safety/alerts/${id}/decide/`,
        method: 'POST',
        body: { decision: 'other', notes: 'Delay pour' },
      },
      {
        path: `/api/v1/safety/alerts/${id}/decide/`,
        method: 'POST',
        body: { decision: 'monitor' },
      },
      {
        path: `/api/v1/safety/alerts/${id}/dismiss/`,
        method: 'POST',
        body: { reason: 'Not relevant' },
      },
      { path: `/api/v1/safety/alerts/${id}/close/`, method: 'POST', body: {} },
      { path: `/api/v1/safety/alerts/${id}/close/`, method: 'POST', body: { notes: 'Done' } },
    ])
  })

  it('reads hazard events and coverage from the approved endpoints', async () => {
    const hazard = alertDto().hazard_event
    const { fetchMock, safety } = await setup(
      json(page([hazard])),
      json(hazard),
      json({
        monitored_projects: 4,
        projects_with_coordinates: 3,
        projects_missing_coordinates: 1,
        alert_creation_enabled: false,
      }),
    )

    const events = await safety.listHazardEvents({
      provider: 'usgs',
      hazardType: 'earthquake',
      alertLevel: 'red',
      providerStatus: 'active',
      project: '22222222-2222-4222-8222-222222222222',
      occurredAfter: '2026-09-01T00:00:00Z',
      occurredBefore: '2026-09-30T00:00:00Z',
      search: 'M 6',
      ordering: '-occurred_at',
    })
    const detail = await safety.getHazardEvent(hazard.id)
    const coverage = await safety.getSafetyMonitoringCoverage()

    expect(url(fetchMock, 0).pathname).toBe('/api/v1/safety/hazard-events/')
    expect([...url(fetchMock, 0).searchParams.keys()].sort()).toEqual([
      'alert_level',
      'hazard_type',
      'occurred_after',
      'occurred_before',
      'ordering',
      'project',
      'provider',
      'provider_status',
      'search',
    ])
    expect(url(fetchMock, 1).pathname).toBe(`/api/v1/safety/hazard-events/${hazard.id}/`)
    expect(url(fetchMock, 2).pathname).toBe('/api/v1/safety/monitoring-coverage/')
    expect(events.items[0]?.provider).toBe('usgs')
    expect(detail.sourceUrl).toContain('earthquake.usgs.gov')
    expect(coverage).toEqual({
      monitoredProjects: 4,
      projectsWithCoordinates: 3,
      projectsMissingCoordinates: 1,
      alertCreationEnabled: false,
    })
    expect(
      fetchMock.mock.calls.every(([target]) => new URL(String(target)).host === 'localhost:8000'),
    ).toBe(true)
  })

  it.each([400, 403, 404, 409, 429, 500])(
    'surfaces HTTP %s as an ApiError with that status',
    async (status) => {
      const { safety, client } = await setup(
        json(
          {
            success: false,
            error: {
              code: status,
              message: 'Request failed.',
              details: { status: ['Only a new safety alert can be acknowledged.'] },
            },
          },
          status,
        ),
      )
      const failure = safety.acknowledgeSafetyAlert('11111111-1111-4111-8111-111111111111')
      await expect(failure).rejects.toBeInstanceOf(client.ApiError)
      await expect(failure).rejects.toMatchObject({ status })
    },
  )

  it('encodes path identifiers so ids cannot alter the request path', async () => {
    const { fetchMock, safety } = await setup(json(alertDto()))
    await safety.getSafetyAlert('../../users')
    expect(url(fetchMock).pathname).toBe('/api/v1/safety/alerts/..%2F..%2Fusers/')
  })
})
