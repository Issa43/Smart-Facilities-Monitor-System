import { describe, expect, it } from 'vitest'
import type { AuditLogEntry } from '@/types'
import {
  auditEntityLabel,
  presentAuditEntry,
  selectLatestOperations,
} from '@/features/super-admin/auditPresentation'

const entry = (overrides: Partial<AuditLogEntry>): AuditLogEntry => ({
  id: 'audit-1',
  actorId: 'cm-1',
  actorName: 'Construction Manager',
  action: 'safety_alert.acknowledged',
  entity: 'safety.projectsafetyalert',
  entityRef: 'earthquake safety alert for project 2222',
  ip: '127.0.0.1',
  createdAt: '2026-09-15T12:00:00Z',
  ...overrides,
})

describe('safety audit presentation', () => {
  it.each([
    ['safety_alert.created', 'إنشاء إنذار سلامة من خطر خارجي'],
    ['safety_alert.escalated', 'تصعيد خطورة إنذار سلامة'],
    ['safety_alert.hazard_withdrawn', 'سحب المصدر لحدث إنذار سلامة'],
    ['safety_alert.acknowledged', 'إقرار الاطلاع على إنذار سلامة'],
    ['safety_alert.action_decided', 'تسجيل قرار لإنذار سلامة'],
    ['safety_alert.dismissed', 'استبعاد إنذار سلامة'],
    ['safety_alert.closed', 'إغلاق إنذار سلامة'],
  ])('presents %s semantically', (action, title) => {
    const presentation = presentAuditEntry(entry({ action }))
    expect(presentation).toMatchObject({ title, entityLabel: 'إنذار سلامة', technical: false })
  })

  it('labels the safety alert entity and suppresses the duplicate API envelope', () => {
    expect(auditEntityLabel('safety.projectsafetyalert')).toBe('إنذار سلامة')
    for (const [action, suffix] of [
      ['safety_alert.acknowledged', 'acknowledge'],
      ['safety_alert.action_decided', 'decide'],
      ['safety_alert.dismissed', 'dismiss'],
      ['safety_alert.closed', 'close'],
    ]) {
      const semantic = entry({ action })
      const envelope = entry({
        id: 'audit-2',
        action: 'api.post',
        entity: 'api_endpoint',
        entityRef: `/api/v1/safety/alerts/11111111-1111-4111-8111-111111111111/${suffix}/`,
        createdAt: '2026-09-15T12:00:01Z',
      })
      expect(selectLatestOperations([envelope, semantic])).toEqual([semantic])
    }
  })
})
