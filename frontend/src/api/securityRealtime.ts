import type { AlertStatus, AlertType, CameraEventType, Severity } from '@/types'
import { API_BASE_URL, getAccessToken } from './client'

export type SecurityRealtimeState =
  'idle' | 'connecting' | 'connected' | 'reconnecting' | 'authentication_failed' | 'stopped'

export interface LiveCameraEvent {
  id: string
  event_type: CameraEventType
  camera_id: string
  facility_id: string
  roi_id: string | null
  track_id: string | null
  object_class: string | null
  confidence: string | null
  detected_at: string
  confirmed_at: string | null
  duration_seconds: string | null
  authorized: boolean | null
  direction: 'entry' | 'exit' | null
  plate_number: string | null
  tamper_type: 'camera_covered' | 'camera_moved' | 'signal_lost' | 'out_of_focus' | null
  security_alert_id: string | null
  status: string
  snapshot: { available: boolean; download_path: string | null }
}

export interface LiveSecurityAlert {
  id: string
  event_id: string | null
  facility_id: string
  camera_id: string | null
  alert_type: AlertType
  severity: Severity
  status: AlertStatus
  is_false_positive: boolean
  created_at: string
  updated_at: string
}

export type SecurityRealtimeMessage =
  | { type: 'security.connection.ready'; version: 1 }
  | {
      type: 'security.camera_event.created'
      version: 1
      event: LiveCameraEvent
      security_alert: LiveSecurityAlert | null
    }
  | { type: 'security.alert.updated'; version: 1; alert: LiveSecurityAlert }

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

const EVENT_TYPES = new Set<CameraEventType>([
  'fire_alert',
  'smoke_alert',
  'intrusion_alert',
  'vehicle_entry',
  'vehicle_exit',
  'tamper_alert',
])
const ALERT_TYPES = new Set<AlertType>([
  'motion',
  'intrusion',
  'fire',
  'smoke',
  'tamper',
  'unauthorized_person',
  'vehicle',
  'emergency',
])
const SEVERITIES = new Set<Severity>(['low', 'medium', 'high', 'critical'])
const ALERT_STATUSES = new Set<AlertStatus>(['new', 'reviewed', 'converted', 'dismissed'])

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function hasOnlyKeys(value: Record<string, unknown>, allowed: string[]): boolean {
  return Object.keys(value).every((key) => allowed.includes(key))
}

function isLiveAlert(value: unknown): value is LiveSecurityAlert {
  if (!isRecord(value)) return false
  return (
    hasOnlyKeys(value, [
      'id',
      'event_id',
      'facility_id',
      'camera_id',
      'alert_type',
      'severity',
      'status',
      'is_false_positive',
      'created_at',
      'updated_at',
    ]) &&
    typeof value.id === 'string' &&
    isNullableString(value.event_id) &&
    typeof value.facility_id === 'string' &&
    isNullableString(value.camera_id) &&
    ALERT_TYPES.has(value.alert_type as AlertType) &&
    SEVERITIES.has(value.severity as Severity) &&
    ALERT_STATUSES.has(value.status as AlertStatus) &&
    typeof value.is_false_positive === 'boolean' &&
    typeof value.created_at === 'string' &&
    typeof value.updated_at === 'string'
  )
}

export function parseSecurityRealtimeMessage(value: unknown): SecurityRealtimeMessage | null {
  if (!isRecord(value) || value.version !== 1 || typeof value.type !== 'string') return null
  if (value.type === 'security.connection.ready') {
    return hasOnlyKeys(value, ['type', 'version']) ? (value as SecurityRealtimeMessage) : null
  }
  if (value.type === 'security.camera_event.created') {
    if (!hasOnlyKeys(value, ['type', 'version', 'event', 'security_alert'])) return null
    if (!isRecord(value.event) || typeof value.event.id !== 'string') return null
    if (
      !hasOnlyKeys(value.event, [
        'id',
        'event_type',
        'camera_id',
        'facility_id',
        'roi_id',
        'track_id',
        'object_class',
        'confidence',
        'detected_at',
        'confirmed_at',
        'duration_seconds',
        'authorized',
        'direction',
        'plate_number',
        'tamper_type',
        'security_alert_id',
        'status',
        'snapshot',
      ])
    )
      return null
    if (typeof value.event.facility_id !== 'string' || typeof value.event.camera_id !== 'string') {
      return null
    }
    if (!EVENT_TYPES.has(value.event.event_type as CameraEventType)) return null
    if (!isNullableString(value.event.security_alert_id)) return null
    for (const field of [
      'roi_id',
      'track_id',
      'object_class',
      'confidence',
      'confirmed_at',
      'duration_seconds',
      'direction',
      'plate_number',
      'tamper_type',
    ]) {
      if (!isNullableString(value.event[field])) return null
    }
    if (typeof value.event.detected_at !== 'string' || typeof value.event.status !== 'string') {
      return null
    }
    if (value.event.authorized !== null && typeof value.event.authorized !== 'boolean') return null
    if (!isRecord(value.event.snapshot)) return null
    if (!hasOnlyKeys(value.event.snapshot, ['available', 'download_path'])) return null
    if (
      typeof value.event.snapshot.available !== 'boolean' ||
      !isNullableString(value.event.snapshot.download_path)
    )
      return null
    if (value.security_alert !== null && !isLiveAlert(value.security_alert)) return null
    return value as unknown as SecurityRealtimeMessage
  }
  if (value.type === 'security.alert.updated') {
    if (!hasOnlyKeys(value, ['type', 'version', 'alert'])) return null
    if (!isLiveAlert(value.alert)) return null
    return value as unknown as SecurityRealtimeMessage
  }
  return null
}

function websocketUrl(): string {
  const url = new URL(API_BASE_URL)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.pathname = '/ws/security/events/'
  url.search = ''
  url.hash = ''
  return url.toString()
}

export function connectSecurityRealtime(options: {
  onMessage: (message: SecurityRealtimeMessage) => void
  onStateChange: (state: SecurityRealtimeState) => void
}): () => void {
  let stopped = false
  let socket: WebSocket | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let retryCount = 0
  const seenCreationIds = new Set<string>()

  const connect = () => {
    const accessToken = getAccessToken()
    if (stopped || !accessToken) {
      options.onStateChange('authentication_failed')
      return
    }
    options.onStateChange(retryCount ? 'reconnecting' : 'connecting')
    socket = new WebSocket(websocketUrl(), ['sflms.jwt', accessToken])
    socket.onopen = () => {
      retryCount = 0
      options.onStateChange('connected')
    }
    socket.onmessage = (event) => {
      let decoded: unknown
      try {
        decoded = JSON.parse(String(event.data))
      } catch {
        return
      }
      const message = parseSecurityRealtimeMessage(decoded)
      if (!message) return
      if (message.type === 'security.camera_event.created') {
        if (seenCreationIds.has(message.event.id)) return
        seenCreationIds.add(message.event.id)
      }
      options.onMessage(message)
    }
    socket.onclose = (event) => {
      socket = null
      if (stopped) return
      if (event.code === 4401 || event.code === 4403) {
        options.onStateChange('authentication_failed')
        return
      }
      retryCount += 1
      options.onStateChange('reconnecting')
      retryTimer = setTimeout(connect, Math.min(30_000, 1_000 * 2 ** Math.min(retryCount, 5)))
    }
  }

  connect()
  return () => {
    stopped = true
    if (retryTimer) clearTimeout(retryTimer)
    socket?.close(1000, 'client_shutdown')
    options.onStateChange('stopped')
  }
}
