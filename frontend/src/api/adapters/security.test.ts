import { describe, expect, it } from 'vitest'

import { incidentFromDto } from './security'

describe('security adapters', () => {
  it('preserves backend incident types outside the predefined alert taxonomy', () => {
    const incident = incidentFromDto({
      id: 'incident-1',
      incident_number: 'INC-2026-0001',
      facility_id: 'facility-1',
      facility_name: 'Main Facility',
      alert_id: null,
      incident_type: 'water_leak',
      description: 'Pipe rupture near the loading area',
      location: 'Loading area',
      severity_level: 'high',
      assigned_to_id: null,
      status: 'open',
      final_report: null,
      closed_by_id: null,
      closed_at: null,
      created_by_id: 'user-1',
      created_at: '2026-08-23T10:00:00Z',
      updated_at: '2026-08-23T10:00:00Z',
    })

    expect(incident.type).toBe('water_leak')
  })
})
