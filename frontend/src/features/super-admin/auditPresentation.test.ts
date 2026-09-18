import { describe, expect, it } from 'vitest'
import type { AuditLogEntry } from '@/types'
import { auditEntityLabel, presentAuditEntry, selectLatestOperations } from './auditPresentation'

function audit(overrides: Partial<AuditLogEntry> = {}): AuditLogEntry {
  return {
    id: 'audit-1',
    actorId: 'admin-1',
    actorName: 'E2E Super Admin',
    action: 'material_request.approved',
    entity: 'materials.materialrequest',
    entityRef: 'Assigned Project - Cement - 3 kg',
    ip: '127.0.0.1',
    createdAt: '2026-09-12T12:00:00Z',
    ...overrides,
  }
}

describe('Super Admin audit presentation', () => {
  it('prioritizes the semantic event and suppresses only its duplicate API envelope', () => {
    const semantic = audit()
    const envelope = audit({
      id: 'audit-2',
      action: 'api.post',
      entity: 'api_endpoint',
      entityRef: '/api/v1/construction/material-requests/request-1/approve/',
      createdAt: '2026-09-12T12:00:02Z',
    })

    const selected = selectLatestOperations([envelope, semantic])

    expect(selected).toEqual([semantic])
    expect(presentAuditEntry(semantic)).toMatchObject({
      title: 'اعتماد طلب توريد مواد',
      entityLabel: 'طلب توريد مواد',
      technical: false,
    })
    expect([envelope, semantic]).toHaveLength(2)
  })

  it('keeps ordering and maps a useful generic event without exposing its path', () => {
    const report = audit({
      id: 'report',
      action: 'api.post',
      entity: 'api_endpoint',
      entityRef: '/api/v1/reports/requests/',
      createdAt: '2026-09-12T12:01:00Z',
    })
    const older = audit({ id: 'older', createdAt: '2026-09-12T11:59:00Z' })

    expect(selectLatestOperations([report, older])).toEqual([report, older])
    const presentation = presentAuditEntry(report)
    expect(presentation.title).toBe('طلب إنشاء تقرير')
    expect(presentation.entityLabel).toBe('—')
    expect(`${presentation.title} ${presentation.reference}`).not.toMatch(
      /api\.post|api_endpoint|\/api\/v1\//,
    )
  })

  it('keeps unknown technical records available with a safe secondary label', () => {
    const entry = audit({
      action: 'api.patch',
      entity: 'api_endpoint',
      entityRef: '/api/v1/internal/future/',
    })

    expect(presentAuditEntry(entry)).toEqual({
      title: 'عملية تقنية',
      entityLabel: '—',
      reference: 'التفاصيل التقنية متاحة في سجل العملية',
      technical: true,
      tone: 'neutral',
    })
    expect(entry.entityRef).toBe('/api/v1/internal/future/')
    expect(auditEntityLabel('api_endpoint')).toBe('سجلات تقنية')
  })

  it('renders security lifecycle semantics and suppresses their API envelope only', () => {
    const semantic = audit({
      action: 'security_alert.dismissed',
      entity: 'security.securityalert',
      entityRef: 'alert-1',
    })
    const envelope = audit({
      id: 'envelope',
      action: 'api.post',
      entity: 'api_endpoint',
      entityRef: '/api/v1/security/alerts/alert-1/dismiss/',
      createdAt: '2026-09-12T12:00:01Z',
    })

    expect(selectLatestOperations([envelope, semantic])).toEqual([semantic])
    expect(presentAuditEntry(semantic)).toMatchObject({
      title: 'تصنيف تنبيه كإنذار كاذب',
      entityLabel: 'تنبيه أمني',
      technical: false,
    })
  })

  it.each([
    ['camera_event.created', 'security.cameraevent', 'حدث كاميرا'],
    ['security_alert.created_from_camera_event', 'security.securityalert', 'تنبيه أمني'],
  ])('prioritizes %s over its CameraEvent POST envelope', (action, entity, entityLabel) => {
    const semantic = audit({ action, entity, entityRef: 'domain-id' })
    const envelope = audit({
      id: `envelope-${action}`,
      action: 'api.post',
      entity: 'api_endpoint',
      entityRef: '/api/v1/camera-events/',
      createdAt: '2026-09-12T12:00:01Z',
    })

    expect(selectLatestOperations([envelope, semantic])).toEqual([semantic])
    expect(presentAuditEntry(semantic)).toMatchObject({ entityLabel, technical: false })
  })

  it.each([
    ['security_alert.reviewed', 'review'],
    ['security_alert.dismissed', 'dismiss'],
    ['security_alert.converted_to_incident', 'convert-to-incident'],
  ])('suppresses the exact lifecycle envelope for %s', (action, endpoint) => {
    const semantic = audit({ action, entity: 'security.securityalert' })
    const envelope = audit({
      id: `envelope-${action}`,
      action: 'api.post',
      entity: 'api_endpoint',
      entityRef: `/api/v1/security/alerts/alert-1/${endpoint}/`,
      createdAt: '2026-09-12T12:00:01Z',
    })

    expect(selectLatestOperations([envelope, semantic])).toEqual([semantic])
  })

  it.each([
    ['camera_roi.created', 'api.post', '/api/v1/roi/', 'security.cameraroi'],
    ['camera_roi.updated', 'api.patch', '/api/v1/roi/roi-1/', 'security.cameraroi'],
    ['camera_roi.disabled', 'api.delete', '/api/v1/roi/roi-1/', 'security.cameraroi'],
    [
      'restricted_schedule.updated',
      'api.patch',
      '/api/v1/restricted-schedules/schedule-1/',
      'security.restrictedzoneschedule',
    ],
    ['virtual_line.created', 'api.post', '/api/v1/virtual-lines/', 'security.virtualline'],
    [
      'authorized_vehicle.disabled',
      'api.delete',
      '/api/v1/vehicles/authorized/vehicle-1/',
      'security.authorizedvehicle',
    ],
    [
      'camera_ai_model.enabled',
      'api.post',
      '/api/v1/cameras/camera-1/active-models/',
      'security.cameraaimodel',
    ],
  ])('suppresses an exact AI configuration envelope for %s', (action, method, path, entity) => {
    const semantic = audit({ action, entity })
    const envelope = audit({
      id: `envelope-${action}`,
      action: method,
      entity: 'api_endpoint',
      entityRef: path,
      createdAt: '2026-09-12T12:00:01Z',
    })

    expect(selectLatestOperations([envelope, semantic])).toEqual([semantic])
    expect(presentAuditEntry(semantic).entityLabel).not.toBe('API request')
  })

  it.each([
    ['ai_ingestion_credential.created', 'api.post', '/api/v1/admin/ai-ingestion-credentials/'],
    [
      'ai_ingestion_credential.rotated',
      'api.post',
      '/api/v1/admin/ai-ingestion-credentials/credential-1/rotate/',
    ],
    [
      'ai_ingestion_credential.revoked',
      'api.post',
      '/api/v1/admin/ai-ingestion-credentials/credential-1/revoke/',
    ],
    [
      'ai_ingestion_credential.scope_added',
      'api.post',
      '/api/v1/admin/ai-ingestion-credentials/credential-1/scopes/',
    ],
    [
      'ai_ingestion_credential.scope_removed',
      'api.delete',
      '/api/v1/admin/ai-ingestion-credentials/credential-1/scopes/camera-1/',
    ],
  ])('suppresses an exact credential envelope for %s', (action, method, path) => {
    const semantic = audit({ action, entity: 'security.aiingestioncredential' })
    const envelope = audit({
      id: `envelope-${action}`,
      action: method,
      entity: 'api_endpoint',
      entityRef: path,
      createdAt: '2026-09-12T12:00:01Z',
    })

    expect(selectLatestOperations([envelope, semantic])).toEqual([semantic])
  })

  it('keeps a technically similar envelope when actor, method, route, or time is not exact', () => {
    const semantic = audit({ action: 'camera_roi.updated', entity: 'security.cameraroi' })
    const envelopes = [
      audit({
        id: 'wrong-actor',
        actorId: 'admin-2',
        action: 'api.patch',
        entity: 'api_endpoint',
        entityRef: '/api/v1/roi/roi-1/',
        createdAt: '2026-09-12T12:00:01Z',
      }),
      audit({
        id: 'wrong-method',
        action: 'api.post',
        entity: 'api_endpoint',
        entityRef: '/api/v1/roi/roi-1/',
        createdAt: '2026-09-12T12:00:01Z',
      }),
      audit({
        id: 'wrong-route',
        action: 'api.patch',
        entity: 'api_endpoint',
        entityRef: '/api/v1/unrelated/roi-1/',
        createdAt: '2026-09-12T12:00:01Z',
      }),
      audit({
        id: 'too-late',
        action: 'api.patch',
        entity: 'api_endpoint',
        entityRef: '/api/v1/roi/roi-1/',
        createdAt: '2026-09-12T12:00:06Z',
      }),
    ]

    expect(selectLatestOperations([...envelopes, semantic], 10)).toEqual([...envelopes, semantic])
  })

  it('does not infer a domain entity from an arbitrary URL or UUID', () => {
    const technical = audit({
      action: 'api.patch',
      entity: 'api_endpoint',
      entityRef: '/api/v1/roi/550e8400-e29b-41d4-a716-446655440000/',
    })

    expect(presentAuditEntry(technical)).toMatchObject({
      entityLabel: '—',
      technical: true,
    })
  })

  it('deduplicates presentation without mutating or removing full audit data', () => {
    const semantic = audit({ action: 'camera_event.created', entity: 'security.cameraevent' })
    const envelope = audit({
      id: 'camera-envelope',
      action: 'api.post',
      entity: 'api_endpoint',
      entityRef: '/api/v1/camera-events/',
      createdAt: '2026-09-12T12:00:01Z',
    })
    const fullAuditData = [envelope, semantic]
    const snapshot = structuredClone(fullAuditData)

    expect(selectLatestOperations(fullAuditData)).toEqual([semantic])
    expect(fullAuditData).toEqual(snapshot)
    expect(fullAuditData).toHaveLength(2)
  })
})
