import { afterEach, describe, expect, it, vi } from 'vitest'

const canonicalRequest = (overrides: Record<string, unknown> = {}) => ({
  id: 'request-1',
  project_id: 'project-1',
  project_name: 'Main Project',
  material: 'material-1',
  material_name: 'Cement',
  unit: 'bag',
  quantity_requested: '25.000',
  reason: 'Stock is below threshold',
  priority: 'urgent',
  status: 'submitted',
  requested_by_id: 'user-1',
  requested_by_name: 'Construction Manager',
  created_at: '2026-08-23T10:00:00Z',
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

describe('construction API contracts', () => {
  it('protects stock counters from material CRUD and records consumption separately', async () => {
    const material = {
      id: 'material-1',
      project_id: 'project-1',
      name: 'Cement',
      unit: 'bag',
      quantity_required: '10.000',
      quantity_used: '0.000',
      quantity_remaining: '10.000',
      min_stock_threshold: '2.000',
    }
    const consumption = {
      id: 'consumption-1',
      material: 'material-1',
      quantity_used: '1.500',
      usage_date: '2026-08-24',
      phase: null,
      created_by_id: 'manager-1',
      created_at: '2026-08-24T10:00:00Z',
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(material))
      .mockResolvedValueOnce(response(consumption))
    vi.stubGlobal('fetch', fetchMock)
    const { consumeMaterial, createMaterial } = await import('./construction')

    await createMaterial({
      projectId: 'project-1',
      name: 'Cement',
      unit: 'bag',
      requiredQty: 10,
      minStockThreshold: 2,
    })
    await consumeMaterial('material-1', 1.5, '2026-08-24')

    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      project: 'project-1',
      name: 'Cement',
      unit: 'bag',
      quantity_required: 10,
      min_stock_threshold: 2,
    })
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain(
      '/construction/materials/material-1/consumption/',
    )
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      quantity: 1.5,
      usage_date: '2026-08-24',
    })
  })

  it('submits the selected material UUID and maps critical priority explicitly', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(canonicalRequest()))
    vi.stubGlobal('fetch', fetchMock)
    const { createMaterialRequest } = await import('./construction')

    const request = await createMaterialRequest({
      projectId: 'project-1',
      materialId: 'material-1',
      requestedQty: 25,
      reason: 'Stock is below threshold',
      priority: 'critical',
    })

    expect(request).toMatchObject({ materialId: 'material-1', priority: 'critical' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))
    expect(body).toMatchObject({ material: 'material-1', priority: 'urgent' })
  })

  it('uses the atomic approve endpoint without a preliminary review transition', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(canonicalRequest({ status: 'approved' })))
      .mockResolvedValueOnce(response(canonicalRequest({ status: 'approved' })))
    vi.stubGlobal('fetch', fetchMock)
    const { setMaterialRequestStatus } = await import('./construction')

    const request = await setMaterialRequestStatus('request-1', 'approved')

    expect(request.status).toBe('approved')
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/approve/')
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/review/'))).toBe(false)
  })
})
