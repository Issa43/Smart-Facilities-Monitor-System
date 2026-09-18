import { afterEach, describe, expect, it, vi } from 'vitest'

const canonicalOrder = (overrides: Record<string, unknown> = {}) => ({
  id: 'order-1',
  reference: 'WO-2026-0001',
  asset_id: 'asset-1',
  asset_name: 'Pump',
  asset_type: 'Mechanical',
  facility_id: 'facility-1',
  type: 'corrective',
  priority: 'urgent',
  description: 'Repair the pump',
  reason: 'Leak',
  assigned_to_id: 'user-1',
  expected_execution_date: '2026-08-25',
  actual_completion_date: null,
  execution_notes: 'Isolated safely',
  cancelled_at: null,
  cancelled_by_id: null,
  cancellation_reason: '',
  status: 'in_progress',
  tasks: [
    {
      id: 'task-1',
      sequence: 1,
      label: 'Isolate power',
      done: true,
      completed_at: '2026-08-23T10:00:00Z',
      completed_by_id: 'user-1',
    },
  ],
  created_by_id: 'user-1',
  created_at: '2026-08-23T09:00:00Z',
  updated_at: '2026-08-23T10:00:00Z',
  ...overrides,
})

const canonicalFault = (overrides: Record<string, unknown> = {}) => ({
  id: 'fault-1',
  reference: 'FLT-2026-0001',
  asset_id: 'asset-1',
  asset_name: 'Pump',
  facility_id: 'facility-1',
  fault_type: 'Leak',
  description: 'Seal leak',
  severity: 'major',
  discovery_time: '2026-08-23T09:00:00Z',
  reported_by_id: 'user-1',
  assigned_engineer_id: 'user-1',
  root_cause: 'Worn seal',
  resolution: 'Seal replaced',
  resolved_at: '2026-08-23T10:00:00Z',
  status: 'resolved',
  created_by_id: 'user-1',
  created_at: '2026-08-23T09:00:00Z',
  updated_at: '2026-08-23T10:00:00Z',
  ...overrides,
})

const canonicalAsset = (overrides: Record<string, unknown> = {}) => ({
  id: 'asset-1',
  facility_id: 'facility-1',
  facility_name: 'Main Facility',
  name: 'Main Chiller',
  asset_type: 'Chiller',
  category: 'custom-hvac',
  serial_number: 'CH-001',
  manufacturer: 'Carrier',
  model: 'X1',
  location_inside_facility: 'Roof',
  installation_date: '2026-01-01',
  operation_date: null,
  current_status: 'operational',
  health_score: '91.50',
  remaining_useful_life: 120,
  last_maintenance_date: null,
  notes: 'Stable',
  created_by_id: 'user-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
  ...overrides,
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('operations API contracts', () => {
  it('uses server pagination and canonical asset filters without rejecting custom categories', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          count: 1,
          total_pages: 3,
          current_page: 2,
          page_size: 20,
          next: null,
          previous: null,
          results: [canonicalAsset()],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { listAssetsPage } = await import('./operations')
    const page = await listAssetsPage({
      page: 2,
      search: 'roof',
      assetType: 'Chiller',
      category: 'custom-hvac',
      manufacturer: 'Carrier',
      ordering: '-updated_at',
    })

    const url = String(fetchMock.mock.calls[0]?.[0])
    expect(url).toContain('page=2')
    expect(url).toContain('search=roof')
    expect(url).toContain('asset_type=Chiller')
    expect(url).toContain('category=custom-hvac')
    expect(page).toMatchObject({ count: 1, totalPages: 3, currentPage: 2 })
    expect(page.results[0]).toMatchObject({
      assetType: 'Chiller',
      category: 'custom-hvac',
      manufacturer: 'Carrier',
      commissionDate: null,
      remainingUsefulLife: 120,
    })
  })

  it('creates an asset in one atomic request and preserves the backend default status', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(canonicalAsset()), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { createAsset } = await import('./operations')
    await createAsset({
      facilityId: 'facility-1',
      name: 'Main Chiller',
      assetType: 'Chiller',
      category: 'custom-hvac',
      manufacturer: 'Carrier',
      model: 'X1',
      locationInFacility: 'Roof',
      serialNumber: 'CH-001',
      installDate: '2026-01-01',
      commissionDate: '',
      notes: 'Stable',
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))
    expect(body).toMatchObject({
      asset_type: 'Chiller',
      category: 'custom-hvac',
      operation_date: null,
    })
    expect(body).not.toHaveProperty('current_status')
    expect(body).not.toHaveProperty('status')
  })

  it('loads filter options from real scoped backend values', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          asset_types: ['Chiller'],
          categories: ['custom-hvac'],
          manufacturers: ['Carrier'],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { getAssetFilterOptions } = await import('./operations')
    await expect(getAssetFilterOptions()).resolves.toEqual({
      assetTypes: ['Chiller'],
      categories: ['custom-hvac'],
      manufacturers: ['Carrier'],
    })
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/assets/filter-options/')
  })

  it('loads server aggregates with the same asset filters as the list', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          total: 2,
          average_health_score: '88.50',
          status_counts: { operational: 1, under_maintenance: 1, out_of_service: 0 },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { getAssetMonitoring } = await import('./operations')
    const result = await getAssetMonitoring({ facilityId: 'facility-1', assetType: 'Chiller' })
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('asset_type=Chiller')
    expect(result).toMatchObject({ total: 2, averageHealthScore: 88.5 })
  })
  it('lists facilities in one paginated request using the server aggregate', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: 'facility-1',
              created_from_project_id: null,
              name: 'Main Facility',
              type: 'commercial',
              location: 'Riyadh',
              operation_start_date: '2026-07-01',
              status: 'operational',
              operations_manager_id: 'user-1',
              asset_count: 7,
              created_by_id: 'admin-1',
              created_at: '2026-06-01T00:00:00Z',
              updated_at: '2026-07-01T00:00:00Z',
            },
          ],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { listFacilities } = await import('./operations')

    const facilities = await listFacilities()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(facilities[0]?.assetCount).toBe(7)
  })

  it('preserves canonical facility assignment and operation date fields', async () => {
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
      created_by_id: 'admin-1',
      created_at: '2026-06-01T00:00:00Z',
      updated_at: '2026-07-01T00:00:00Z',
    })

    expect(facility.operationStartDate).toBe('2026-07-01')
    expect(facility.operationsManagerId).toBe('user-1')
  })

  it('preserves reference, notes, checklist, and cancellation metadata', async () => {
    const { workOrderFromDto } = await import('./adapters/operations')

    const order = workOrderFromDto(
      canonicalOrder({
        status: 'cancelled',
        cancelled_at: '2026-08-23T11:00:00Z',
        cancelled_by_id: 'admin-1',
        cancellation_reason: 'Duplicate order',
      }) as never,
    )

    expect(order).toMatchObject({
      reference: 'WO-2026-0001',
      notes: 'Isolated safely',
      status: 'cancelled',
      cancelledById: 'admin-1',
      cancellationReason: 'Duplicate order',
    })
    expect(order.tasks[0]).toMatchObject({ sequence: 1, done: true, completedById: 'user-1' })
  })

  it('updates notes without sending an empty maintenance-order patch', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(canonicalOrder({ execution_notes: 'Updated note' })), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { updateWorkOrder } = await import('./operations')

    const order = await updateWorkOrder('order-1', { notes: 'Updated note' })

    expect(order.notes).toBe('Updated note')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/maintenance/orders/order-1/notes/')
  })

  it('sends task labels when creating a work order', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(canonicalOrder()), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { createWorkOrder } = await import('./operations')

    await createWorkOrder({
      assetId: 'asset-1',
      assetType: 'Mechanical',
      facilityId: 'facility-1',
      maintenanceType: 'corrective',
      reason: 'Leak',
      description: 'Repair the pump',
      priority: 'high',
      scheduledDate: '2026-08-25',
      assignedToId: 'user-1',
      tasks: ['Isolate power', 'Replace seal'],
    })

    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toMatchObject({
      asset_type: 'Mechanical',
      tasks: ['Isolate power', 'Replace seal'],
      expected_execution_date: '2026-08-25',
    })
  })

  it('preserves fault reference and resolution and exposes canonical closure', async () => {
    const { faultFromDto } = await import('./adapters/operations')
    const fault = faultFromDto(canonicalFault() as never)
    expect(fault).toMatchObject({
      reference: 'FLT-2026-0001',
      rootCause: 'Worn seal',
      resolution: 'Seal replaced',
      resolvedAt: '2026-08-23T10:00:00Z',
    })

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(canonicalFault({ status: 'closed' })), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { setFaultStatus } = await import('./operations')
    await setFaultStatus('fault-1', 'closed')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/faults/fault-1/close/')
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('POST')
  })
})
