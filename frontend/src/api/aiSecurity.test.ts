// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cameraEventFromDto } from './aiSecurity'
import { alertFromDto } from './adapters/security'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('AI security frontend contracts', () => {
  it('preserves event-specific fields and exposes only protected snapshot metadata', () => {
    const event = cameraEventFromDto({
      id: 'event-1',
      event_type: 'vehicle_entry',
      camera_id: 'camera-1',
      camera_code: 'CAM-01',
      facility_id: 'facility-1',
      facility_name: 'Main',
      roi_id: null,
      roi_identifier: null,
      track_id: 'track-1',
      confidence: null,
      object_class: null,
      detected_at: '2026-09-14T10:00:00Z',
      confirmed_at: null,
      duration_seconds: null,
      bbox: null,
      bbox_plate: { x1: 1, y1: 2, x2: 3, y2: 4 },
      bbox_vehicle: { x1: 5, y1: 6, x2: 7, y2: 8 },
      crossing_centroid: { x: 6, y: 7 },
      entered_roi_at: null,
      time_restricted: null,
      plate_number: 'ABC123',
      plate_confidence: '0.92',
      ocr_confidence: '0.88',
      vehicle_type: 'car',
      vehicle_confidence: '0.96',
      direction: 'entry',
      authorized: false,
      tamper_type: null,
      status: 'new',
      security_alert_id: 'alert-1',
      snapshot_available: true,
      snapshot_download_url: '/api/v1/camera-events/event-1/snapshot/',
      created_at: '2026-09-14T10:00:01Z',
      updated_at: '2026-09-14T10:00:01Z',
    })
    expect(event).toMatchObject({
      plateNumber: 'ABC123',
      authorized: false,
      plateConfidence: 0.92,
      securityAlertId: 'alert-1',
      snapshotAvailable: true,
    })
    expect(JSON.stringify(event)).not.toContain('security/camera-events/')
  })

  it('preserves alert confidence, camera, ROI, event type and tamper', () => {
    const alert = alertFromDto({
      id: 'alert-1',
      facility_id: 'facility-1',
      facility_name: 'Main',
      alert_type: 'tamper',
      location: 'Gate',
      severity_level: 'critical',
      source: 'CAM-01',
      confidence_score: '0.91',
      camera_event_id: 'event-1',
      event_type: 'tamper_alert',
      camera_id: 'camera-1',
      camera_code: 'CAM-01',
      roi_id: null,
      roi_identifier: null,
      snapshot_available: false,
      snapshot_download_url: null,
      status: 'new',
      is_false_positive: false,
      reviewed_by_id: null,
      review_notes: '',
      created_by_id: null,
      created_at: '2026-09-14T10:00:01Z',
      updated_at: '2026-09-14T10:00:01Z',
    })
    expect(alert).toMatchObject({
      type: 'tamper',
      severity: 'critical',
      confidence: 0.91,
      cameraCode: 'CAM-01',
      eventType: 'tamper_alert',
    })
  })

  it('downloads snapshots through the authenticated protected endpoint', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response('jpeg', { status: 200, headers: { 'Content-Type': 'image/jpeg' } }),
      )
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:event')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const { setAuthTokens } = await import('./client')
    const { downloadCameraEventSnapshot } = await import('./aiSecurity')
    setAuthTokens({ access: 'browser-access', refresh: 'browser-refresh' })
    await downloadCameraEventSnapshot('event-1')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/camera-events/event-1/snapshot/')
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('Authorization')).toBe(
      'Bearer browser-access',
    )
  })

  it('uses real event-detail, filter, ROI, and active-model routes', async () => {
    const eventDto = {
      id: 'event-1',
      event_type: 'fire_alert',
      camera_id: 'camera-1',
      camera_code: 'CAM-01',
      facility_id: 'facility-1',
      facility_name: 'Main',
      roi_id: 'roi-1',
      roi_identifier: 'fire-zone',
      track_id: 'track-1',
      confidence: '0.9',
      object_class: 'fire',
      detected_at: '2026-09-14T10:00:00Z',
      confirmed_at: '2026-09-14T10:00:03Z',
      duration_seconds: '3',
      bbox: { x1: 1, y1: 2, x2: 3, y2: 4 },
      bbox_plate: null,
      bbox_vehicle: null,
      crossing_centroid: null,
      entered_roi_at: null,
      time_restricted: null,
      plate_number: null,
      plate_confidence: null,
      ocr_confidence: null,
      vehicle_type: null,
      vehicle_confidence: null,
      direction: null,
      authorized: null,
      tamper_type: null,
      status: 'new',
      security_alert_id: 'alert-1',
      snapshot_available: true,
      snapshot_download_url: '/api/v1/camera-events/event-1/snapshot/',
      created_at: '2026-09-14T10:00:01Z',
      updated_at: '2026-09-14T10:00:01Z',
    }
    const roiDto = {
      id: 'roi-1',
      camera_id: 'camera-1',
      identifier: 'fire-zone',
      name: 'Fire zone',
      polygon: [
        { x: 0, y: 0 },
        { x: 1, y: 0 },
        { x: 0, y: 1 },
      ],
      is_active: true,
    }
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      })
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json({ count: 1, next: null, results: [eventDto] }))
      .mockResolvedValueOnce(json(eventDto))
      .mockResolvedValueOnce(json(roiDto, 201))
      .mockResolvedValueOnce(
        json(
          {
            id: 'model-1',
            camera_id: 'camera-1',
            model_identifier: 'tamper',
            is_active: true,
            updated_at: eventDto.updated_at,
          },
          201,
        ),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const api = await import('./aiSecurity')
    await api.listCameraEvents({ camera: 'camera-1', eventType: 'fire_alert', authorized: false })
    expect(await api.getCameraEvent('event-1')).toMatchObject({
      id: 'event-1',
      roiIdentifier: 'fire-zone',
    })
    await api.createCameraRoi({
      camera: 'camera-1',
      identifier: 'fire-zone',
      name: 'Fire zone',
      polygon: roiDto.polygon,
    })
    await api.enableCameraAiModel('camera-1', 'tamper')
    await api.disableCameraAiModel('camera-1', 'tamper')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      '/camera-events/?camera=camera-1&event_type=fire_alert&authorized=false',
    )
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({
      camera: 'camera-1',
      identifier: 'fire-zone',
      name: 'Fire zone',
      polygon: roiDto.polygon,
    })
    expect(String(fetchMock.mock.calls[4]?.[0])).toContain(
      '/cameras/camera-1/active-models/tamper/',
    )
    expect(fetchMock.mock.calls[4]?.[1]?.method).toBe('DELETE')
  })
})
