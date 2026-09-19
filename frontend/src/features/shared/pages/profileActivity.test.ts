import { describe, expect, it } from 'vitest'
import type { AuditLogEntry } from '@/types'
import { selectProfileActivities } from './profileActivity'

function audit(overrides: Partial<AuditLogEntry> = {}): AuditLogEntry {
  return {
    id: 'audit-1',
    actorId: 'user-1',
    actorName: 'Operations Manager',
    action: 'asset.created',
    entity: 'assets.asset',
    entityRef: 'Main Pump (PUMP-1)',
    ip: '127.0.0.1',
    createdAt: '2026-09-11T12:00:00Z',
    ...overrides,
  }
}

describe('selectProfileActivities', () => {
  it('presents asset semantic events in Arabic', () => {
    const [activity] = selectProfileActivities([audit()], 'user-1')

    expect(activity.title).toBe('إنشاء أصل')
    expect(activity.body).toContain('Main Pump (PUMP-1)')
    expect(`${activity.title} ${activity.body}`).not.toMatch(
      /asset\.created|api_endpoint|\/api\/v1\//,
    )
  })

  it('suppresses the duplicate generic Asset envelope while preserving the semantic event', () => {
    const entries = [
      audit(),
      audit({
        id: 'audit-2',
        action: 'api.post',
        entity: 'api_endpoint',
        entityRef: '/api/v1/assets/',
      }),
    ]

    const activities = selectProfileActivities(entries, 'user-1')

    expect(activities).toHaveLength(1)
    expect(activities[0].title).toBe('إنشاء أصل')
    expect(entries[1].action).toBe('api.post')
  })

  it('presents report requests without exposing API terminology or paths', () => {
    const [activity] = selectProfileActivities(
      [
        audit({
          action: 'api.post',
          entity: 'api_endpoint',
          entityRef: '/api/v1/reports/requests/',
        }),
      ],
      'user-1',
    )

    expect(activity).toMatchObject({
      title: 'طلب إنشاء تقرير',
      body: 'تم إرسال طلب جديد لإنشاء تقرير.',
    })
    expect(`${activity.title} ${activity.body}`).not.toMatch(/api\.post|api_endpoint|\/api\/v1\//)
  })

  it('uses a localized safe fallback for unknown events', () => {
    const [activity] = selectProfileActivities(
      [audit({ action: 'future.event', entity: 'internal.model', entityRef: 'secret-ref' })],
      'user-1',
    )

    expect(activity).toMatchObject({
      title: 'نشاط داخل النظام',
      body: 'تم تنفيذ إجراء مسجل داخل النظام.',
    })
    expect(`${activity.title} ${activity.body}`).not.toContain('future.event')
    expect(`${activity.title} ${activity.body}`).not.toContain('internal.model')
    expect(`${activity.title} ${activity.body}`).not.toContain('secret-ref')
  })

  it('returns an empty activity list when the actor has no presentable entries', () => {
    expect(selectProfileActivities([], 'user-1')).toEqual([])
    expect(selectProfileActivities([audit({ actorId: 'user-2' })], 'user-1')).toEqual([])
  })
})
