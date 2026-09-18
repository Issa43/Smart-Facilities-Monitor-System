// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest'
import { connectSecurityRealtime, parseSecurityRealtimeMessage } from './securityRealtime'
import { clearAuthTokens, setAuthTokens } from './client'

afterEach(() => {
  clearAuthTokens()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

const validCreated = {
  type: 'security.camera_event.created',
  version: 1,
  event: {
    id: 'event-1',
    event_type: 'tamper_alert',
    camera_id: 'camera-1',
    facility_id: 'facility-1',
    roi_id: null,
    track_id: null,
    object_class: null,
    confidence: '0.910000',
    detected_at: '2026-09-14T10:00:00Z',
    confirmed_at: null,
    duration_seconds: null,
    authorized: null,
    direction: null,
    plate_number: null,
    tamper_type: 'camera_covered',
    security_alert_id: 'alert-1',
    status: 'new',
    snapshot: {
      available: true,
      download_path: '/api/v1/camera-events/event-1/snapshot/',
    },
  },
  security_alert: {
    id: 'alert-1',
    event_id: 'event-1',
    facility_id: 'facility-1',
    camera_id: 'camera-1',
    alert_type: 'tamper',
    severity: 'critical',
    status: 'new',
    is_false_positive: false,
    created_at: '2026-09-14T10:00:01Z',
    updated_at: '2026-09-14T10:00:01Z',
  },
}

describe('security realtime contract', () => {
  it('accepts the documented envelope and rejects unknown or malformed values', () => {
    expect(parseSecurityRealtimeMessage(validCreated)?.type).toBe('security.camera_event.created')
    expect(
      parseSecurityRealtimeMessage({
        ...validCreated,
        event: { ...validCreated.event, event_type: 'raw_detection' },
      }),
    ).toBeNull()
    expect(
      parseSecurityRealtimeMessage({
        ...validCreated,
        security_alert: { ...validCreated.security_alert, severity: 'urgent' },
      }),
    ).toBeNull()
    expect(
      parseSecurityRealtimeMessage({ ...validCreated, storage_key: 'private/key.jpg' }),
    ).toBeNull()
  })

  it('uses the JWT subprotocol without a query-string token and deduplicates creations', () => {
    const instances: Array<{
      url: string
      protocols: string[]
      onmessage: ((event: { data: string }) => void) | null
    }> = []
    class FakeWebSocket {
      static OPEN = 1
      onopen: (() => void) | null = null
      onmessage: ((event: { data: string }) => void) | null = null
      onclose: ((event: { code: number }) => void) | null = null
      constructor(
        public url: string,
        public protocols: string[],
      ) {
        instances.push(this)
      }
      close() {}
    }
    vi.stubGlobal('WebSocket', FakeWebSocket)
    setAuthTokens({ access: 'jwt-value', refresh: 'refresh-value' })
    const messages: unknown[] = []
    const stop = connectSecurityRealtime({
      onMessage: (message) => messages.push(message),
      onStateChange: () => undefined,
    })
    expect(instances[0].url).toContain('/ws/security/events/')
    expect(instances[0].url).not.toContain('jwt-value')
    expect(instances[0].protocols).toEqual(['sflms.jwt', 'jwt-value'])
    instances[0].onmessage?.({ data: JSON.stringify(validCreated) })
    instances[0].onmessage?.({ data: JSON.stringify(validCreated) })
    expect(messages).toHaveLength(1)
    stop()
  })

  it('reports authentication failure instead of connecting without a token', () => {
    const states: string[] = []
    connectSecurityRealtime({
      onMessage: () => undefined,
      onStateChange: (state) => states.push(state),
    })
    expect(states).toEqual(['authentication_failed'])
  })
})
