import { afterEach, describe, expect, it, vi } from 'vitest'
import { canAccessRoleRoute } from '@/routes/routeAccess'
import { ROLE_ROUTES } from '@/routes/routeConfig'

const projectDto = (overrides: Record<string, unknown> = {}) => ({
  id: 'project-1',
  name: 'Atomic Project',
  facility_id: null,
  facility_type: 'commercial',
  description: 'Atomic project and manager assignment',
  location: 'Riyadh',
  latitude: null,
  longitude: null,
  image_available: false,
  start_date: '2026-08-24',
  expected_completion_date: '2026-11-24',
  actual_completion_date: null,
  status: 'planning',
  progress_percentage: '0.00',
  is_overdue: false,
  primary_manager_id: 'manager-1',
  current_phase_name: null,
  created_by_id: 'admin-1',
  created_at: '2026-08-24T00:00:00Z',
  updated_at: '2026-08-24T00:00:00Z',
  ...overrides,
})

const response = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('Super Admin project operations', () => {
  it('creates a project and primary-manager assignment through one request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(projectDto()))
    vi.stubGlobal('fetch', fetchMock)
    const { createProject } = await import('@/api/construction')

    const project = await createProject({
      name: 'Atomic Project',
      facilityType: 'commercial',
      description: 'Atomic project and manager assignment',
      location: 'Riyadh',
      startDate: '2026-08-24T00:00:00Z',
      expectedEndDate: '2026-11-24T00:00:00Z',
      status: 'planning',
      constructionManagerId: 'manager-1',
    })

    expect(project.constructionManagerId).toBe('manager-1')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, request] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/projects/')
    expect(request.method).toBe('POST')
    expect(JSON.parse(String(request.body))).toMatchObject({
      name: 'Atomic Project',
      primary_manager_id: 'manager-1',
    })
  })

  it('updates project metadata and manager through one request', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(response(projectDto({ primary_manager_id: 'manager-2' })))
    vi.stubGlobal('fetch', fetchMock)
    const { updateProject } = await import('@/api/construction')

    const project = await updateProject('project-1', {
      name: 'Updated Atomic Project',
      constructionManagerId: 'manager-2',
    })

    expect(project.constructionManagerId).toBe('manager-2')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, request] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/projects/project-1/')
    expect(request.method).toBe('PATCH')
    expect(JSON.parse(String(request.body))).toEqual({
      name: 'Updated Atomic Project',
      primary_manager_id: 'manager-2',
    })
  })
})

describe('Super Admin operational navigation', () => {
  it('can enter every role route while ordinary roles remain isolated', () => {
    expect(canAccessRoleRoute('super_admin', 'construction_manager')).toBe(true)
    expect(canAccessRoleRoute('super_admin', 'operations_manager')).toBe(true)
    expect(canAccessRoleRoute('super_admin', 'security_officer')).toBe(true)
    expect(canAccessRoleRoute('operations_manager', 'security_officer')).toBe(false)
    expect(canAccessRoleRoute('construction_manager', 'operations_manager')).toBe(false)
  })

  it('exposes every Batch 4 operational area in the Super Admin navigation', () => {
    const paths = ROLE_ROUTES.super_admin.nav.flatMap((group) =>
      group.items.map((item) => item.path),
    )

    expect(paths).toEqual(
      expect.arrayContaining([
        '/admin/projects',
        '/admin/material-requests',
        '/operations/facilities',
        '/operations/assets',
        '/operations/work-orders',
        '/security/alerts',
        '/security/incidents',
        '/security/cameras',
        '/security/documents',
        '/admin/reports',
        '/admin/notifications',
      ]),
    )
  })
})
