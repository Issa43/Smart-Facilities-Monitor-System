import { afterEach, describe, expect, it, vi } from 'vitest'

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

const requirementDto = (overrides: Record<string, unknown> = {}) => ({
  facility_id: 'facility-1',
  required_camera_count: 5,
  previous_required_camera_count: 3,
  existing: 3,
  created: 2,
  surplus: 0,
  camera_count: 5,
  created_camera_ids: ['cam-4', 'cam-5'],
  cameras: [
    {
      id: 'cam-4',
      facility_id: 'facility-1',
      asset_id: 'asset-4',
      code: 'CAM-ABCDEF012345-004',
      name: 'Camera 004',
      zone: 'Unassigned',
      status: 'offline',
      last_seen_at: null,
      created_at: '2026-09-01T00:00:00Z',
    },
  ],
  ...overrides,
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('facility camera requirement API', () => {
  it('PUTs the absolute count to the facility endpoint and maps the result', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(requirementDto()))
    vi.stubGlobal('fetch', fetchMock)
    const { setFacilityCameraRequirement } = await import('./operations')

    const result = await setFacilityCameraRequirement('facility-1', 5)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      '/facilities/facility-1/camera-requirement/',
    )
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('PUT')
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      required_camera_count: 5,
    })
    expect(result).toMatchObject({
      facilityId: 'facility-1',
      requiredCameraCount: 5,
      previousRequiredCameraCount: 3,
      existing: 3,
      created: 2,
      surplus: 0,
      cameraCount: 5,
      createdCameraIds: ['cam-4', 'cam-5'],
    })
    expect(result.cameras[0]).toEqual({
      id: 'cam-4',
      facilityId: 'facility-1',
      assetId: 'asset-4',
      code: 'CAM-ABCDEF012345-004',
      name: 'Camera 004',
      zone: 'Unassigned',
      status: 'offline',
      lastSeenAt: null,
      createdAt: '2026-09-01T00:00:00Z',
    })
  })

  it('reports surplus without implying any removal', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            requirementDto({ required_camera_count: 3, existing: 5, created: 0, surplus: 2 }),
          ),
        ),
    )
    const { setFacilityCameraRequirement } = await import('./operations')

    const result = await setFacilityCameraRequirement('facility-1', 3)

    expect(result.surplus).toBe(2)
    expect(result.created).toBe(0)
  })

  it('loads the current requirement with a GET', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(requirementDto({ required_camera_count: null, created: 0 })))
    vi.stubGlobal('fetch', fetchMock)
    const { getFacilityCameraRequirement } = await import('./operations')

    const result = await getFacilityCameraRequirement('facility-1')

    expect(fetchMock.mock.calls[0]?.[1]?.method ?? 'GET').toBe('GET')
    expect(result.requiredCameraCount).toBeNull()
  })

  it('surfaces the server validation message on conflict', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            { status: ['Cameras cannot be provisioned for a decommissioned facility.'] },
            409,
          ),
        ),
    )
    const { setFacilityCameraRequirement } = await import('./operations')

    await expect(setFacilityCameraRequirement('facility-1', 2)).rejects.toThrow(
      'Cameras cannot be provisioned for a decommissioned facility.',
    )
  })

  it('maps the facility requirement and camera count onto Facility', async () => {
    const { facilityFromDto } = await import('./adapters/operations')

    const facility = facilityFromDto({
      id: 'facility-1',
      created_from_project_id: 'project-1',
      name: 'Main Facility',
      type: 'commercial',
      location: 'Riyadh',
      operation_start_date: '2026-07-01',
      status: 'operational',
      operations_manager_id: 'user-1',
      required_camera_count: 4,
      camera_count: 3,
      created_by_id: 'admin-1',
      created_at: '2026-06-01T00:00:00Z',
      updated_at: '2026-07-01T00:00:00Z',
    })

    expect(facility.requiredCameraCount).toBe(4)
    expect(facility.cameraCount).toBe(3)
  })
})

describe('camera maintenance report API', () => {
  const reportDto = (overrides: Record<string, unknown> = {}) => ({
    id: 'fault-1',
    reference: 'FLT-ABC123',
    asset_id: 'asset-1',
    fault_type: 'camera_maintenance',
    description: 'Lens cracked',
    severity: 'major',
    status: 'reported',
    discovery_time: '2026-09-01T00:00:00Z',
    reported_by_id: 'officer-1',
    created_at: '2026-09-01T00:00:00Z',
    camera_id: 'cam-1',
    created: true,
    ...overrides,
  })

  it('POSTs the description and the backend severity value', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(reportDto(), 201))
    vi.stubGlobal('fetch', fetchMock)
    const { reportCameraMaintenance } = await import('./security')

    const result = await reportCameraMaintenance('cam-1', {
      description: 'Lens cracked',
      severity: 'high',
    })

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      '/security/cameras/cam-1/report-maintenance/',
    )
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('POST')
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      description: 'Lens cracked',
      severity: 'major',
    })
    expect(result).toEqual({
      id: 'fault-1',
      reference: 'FLT-ABC123',
      cameraId: 'cam-1',
      status: 'reported',
      severity: 'high',
      description: 'Lens cracked',
      created: true,
    })
  })

  it('keeps the existing open report when the server returns it', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(reportDto({ created: false }))))
    const { reportCameraMaintenance } = await import('./security')

    const result = await reportCameraMaintenance('cam-1', {
      description: 'Again',
      severity: 'medium',
    })

    expect(result.created).toBe(false)
    expect(result.reference).toBe('FLT-ABC123')
  })
})
