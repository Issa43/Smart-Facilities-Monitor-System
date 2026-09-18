import { afterEach, describe, expect, it, vi } from 'vitest'

const projectDto = {
  id: 'project-1',
  name: 'Project One',
  facility_id: null,
  facility_type: 'commercial',
  description: 'Project description',
  location: 'Cairo',
  latitude: null,
  longitude: null,
  image_available: false,
  start_date: '2026-08-01',
  expected_completion_date: '2026-12-01',
  actual_completion_date: null,
  status: 'in_progress',
  progress_percentage: '25.00',
  is_overdue: false,
  primary_manager_id: 'manager-1',
  primary_manager_name: 'Scoped Manager',
  current_phase_name: 'Foundation',
  created_by_id: 'admin-1',
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-23T10:00:00Z',
}

const phaseDto = {
  id: 'phase-1',
  project_id: 'project-1',
  name: 'Foundation',
  description: 'Foundation work',
  sequence_number: 1,
  start_date: '2026-08-01',
  expected_completion_date: '2026-09-01',
  actual_start_date: null,
  actual_completion_date: null,
  initial_progress: '0.00',
  current_progress: '0.00',
  priority: 'high',
  status: 'not_started',
  approved_by_id: null,
  approved_at: null,
  created_by_id: 'manager-1',
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-23T10:00:00Z',
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

const page = (results: unknown[]) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('construction project and phase contracts', () => {
  it('edits assigned project metadata through the scoped construction endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(projectDto))
    vi.stubGlobal('fetch', fetchMock)
    const { updateAssignedProject } = await import('./construction')

    const project = await updateAssignedProject('project-1', {
      name: 'Updated project',
      location: 'Giza',
      expectedEndDate: '2027-01-15',
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(project.constructionManagerName).toBe('Scoped Manager')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/construction/projects/project-1/')
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('PATCH')
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      name: 'Updated project',
      location: 'Giza',
      expected_completion_date: '2027-01-15',
    })
  })

  it('uses the nested phase contracts for edit and lifecycle-safe delete', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(phaseDto))
      .mockResolvedValueOnce(jsonResponse(page([])))
      .mockResolvedValueOnce(jsonResponse({ ...phaseDto, name: 'Edited phase' }))
      .mockResolvedValueOnce(jsonResponse(phaseDto))
      .mockResolvedValueOnce(jsonResponse(page([])))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const { deleteStage, updateStage } = await import('./construction')

    await updateStage('phase-1', { name: 'Edited phase' })
    await deleteStage('phase-1')

    const patchCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
    const deleteCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'DELETE')
    expect(String(patchCall?.[0])).toContain('/projects/project-1/phases/phase-1/')
    expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual({ name: 'Edited phase' })
    expect(String(deleteCall?.[0])).toContain('/projects/project-1/phases/phase-1/')
  })

  it('maps the complete review history and sends required return reasons', async () => {
    const reviews = [
      {
        id: 'review-2',
        phase_id: 'phase-1',
        decision: 'rejected',
        disposition: 'final_rejection',
        reason: 'Final safety finding',
        created_by_id: 'manager-1',
        created_at: '2026-08-24T10:00:00Z',
      },
      {
        id: 'review-1',
        phase_id: 'phase-1',
        decision: 'rejected',
        disposition: 'needs_modification',
        reason: 'Correct the evidence',
        created_by_id: 'manager-1',
        created_at: '2026-08-23T10:00:00Z',
      },
    ]
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(phaseDto))
      .mockResolvedValueOnce(jsonResponse(page(reviews)))
      .mockResolvedValueOnce(jsonResponse(phaseDto))
      .mockResolvedValueOnce(jsonResponse(page(reviews)))
      .mockResolvedValueOnce(jsonResponse(reviews[1], 201))
      .mockResolvedValueOnce(jsonResponse(phaseDto))
      .mockResolvedValueOnce(jsonResponse(page(reviews)))
    vi.stubGlobal('fetch', fetchMock)
    const { listStageReviews, reviewStage } = await import('./construction')

    const history = await listStageReviews('phase-1')
    await reviewStage('phase-1', 'return', 'Correct the evidence')

    expect(history.map((entry) => entry.reason)).toEqual([
      'Final safety finding',
      'Correct the evidence',
    ])
    const returnCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes('/request-modification/'),
    )
    expect(JSON.parse(String(returnCall?.[1]?.body))).toEqual({
      reason: 'Correct the evidence',
    })
  })
})
