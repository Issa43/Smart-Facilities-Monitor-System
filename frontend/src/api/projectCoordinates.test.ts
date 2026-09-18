import { beforeEach, describe, expect, it, vi } from 'vitest'
import { projectFromDto, type ProjectDto } from './adapters/projects'

const mocks = vi.hoisted(() => ({ apiRequest: vi.fn() }))

vi.mock('./client', () => ({
  apiRequest: mocks.apiRequest,
  downloadProtectedFile: vi.fn(),
}))

const DTO: ProjectDto = {
  id: 'p1',
  name: 'diana test',
  facility_id: null,
  facility_type: 'commercial',
  description: 'desc',
  location: 'almouzena',
  latitude: null,
  longitude: null,
  image_available: false,
  start_date: '2026-01-01',
  expected_completion_date: '2026-06-01',
  actual_completion_date: null,
  status: 'in_progress',
  progress_percentage: '0',
  is_overdue: false,
  primary_manager_id: null,
  primary_manager_name: null,
  current_phase_name: null,
  created_by_id: 'u1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

describe('project coordinates — reading', () => {
  it('parses the decimal strings DRF sends into numbers', () => {
    const project = projectFromDto({ ...DTO, latitude: '34.802100', longitude: '38.996800' })

    expect(project.latitude).toBe(34.8021)
    expect(project.longitude).toBe(38.9968)
  })

  it('keeps an unlocated project null rather than collapsing it to 0', () => {
    const project = projectFromDto(DTO)

    // 0,0 is a real point in the Gulf of Guinea; a project with no location
    // must not silently acquire one.
    expect(project.latitude).toBeNull()
    expect(project.longitude).toBeNull()
  })

  it('treats an empty or unparseable value as absent', () => {
    expect(projectFromDto({ ...DTO, latitude: '' }).latitude).toBeNull()
    expect(projectFromDto({ ...DTO, longitude: 'not-a-number' }).longitude).toBeNull()
  })

  it('preserves negative coordinates', () => {
    const project = projectFromDto({ ...DTO, latitude: '-33.868800', longitude: '-70.503000' })

    expect(project.latitude).toBeCloseTo(-33.8688, 6)
    expect(project.longitude).toBeCloseTo(-70.503, 6)
  })
})

describe('project coordinates — writing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.apiRequest.mockResolvedValue(DTO)
  })

  async function createWith(input: Record<string, unknown>) {
    const { createProject } = await import('./construction')
    await createProject({
      name: 'n',
      facilityType: 'commercial',
      description: 'd',
      location: 'almouzena',
      startDate: '2026-01-01',
      expectedEndDate: '2026-06-01',
      status: 'planning',
      constructionManagerId: 'm1',
      ...input,
    } as Parameters<typeof createProject>[0])
    return mocks.apiRequest.mock.calls[0][1].body as Record<string, unknown>
  }

  it('sends the picked point as decimal strings', async () => {
    const body = await createWith({ latitude: 34.8021, longitude: 38.9968 })

    expect(body.latitude).toBe('34.802100')
    expect(body.longitude).toBe('38.996800')
  })

  it('rounds a raw map click to the six decimals the column allows', async () => {
    // A Leaflet click yields full float precision; DecimalField(max_digits=9,
    // decimal_places=6) rejects anything longer.
    const body = await createWith({
      latitude: 34.80210123456789,
      longitude: 38.99680987654321,
    })

    expect(body.latitude).toBe('34.802101')
    expect(body.longitude).toBe('38.996810')
    for (const value of [body.latitude, body.longitude] as string[]) {
      expect(value.replace('-', '').replace('.', '').length).toBeLessThanOrEqual(9)
      expect(value.split('.')[1]).toHaveLength(6)
    }
  })

  it('never rounds a coordinate past the range the model validates', async () => {
    const body = await createWith({ latitude: 89.99999999, longitude: -179.99999999 })

    expect(Number(body.latitude)).toBeLessThanOrEqual(90)
    expect(Number(body.longitude)).toBeGreaterThanOrEqual(-180)
  })

  it('keeps a full-width negative coordinate within nine digits', async () => {
    const body = await createWith({ latitude: -12.3456789, longitude: -123.4567891 })

    expect(body.latitude).toBe('-12.345679')
    expect(body.longitude).toBe('-123.456789')
    expect((body.longitude as string).replace('-', '').replace('.', '')).toHaveLength(9)
  })

  it('sends no coordinates at all when none were picked', async () => {
    const body = await createWith({ latitude: null, longitude: null })

    // Absent, not null: the serializer must not be asked to clear a value the
    // user never touched.
    expect('latitude' in body).toBe(false)
    expect('longitude' in body).toBe(false)
  })

  it('omits coordinates entirely when the caller does not mention them', async () => {
    const body = await createWith({})

    expect('latitude' in body).toBe(false)
    expect('longitude' in body).toBe(false)
  })

  it('still sends the textual location, which is never derived from the point', async () => {
    const body = await createWith({ latitude: 34.8021, longitude: 38.9968 })

    expect(body.location).toBe('almouzena')
  })
})
