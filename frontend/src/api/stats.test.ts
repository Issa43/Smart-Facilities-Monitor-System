import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearAuthTokens } from './client'
import { getAdminStats } from './stats'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  clearAuthTokens()
})

describe('admin analytics API mapping', () => {
  it('maps database-derived delayed and distribution values without adding a planned series', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            total_projects: 3,
            active_projects: 2,
            delayed_projects: 1,
            overall_progress: 33.33,
            operational_facilities: 1,
            total_assets: 4,
            asset_health: 82.5,
            open_work_orders: 2,
            overdue_work_orders: 1,
            open_incidents: 1,
            critical_alerts: 0,
            active_users: 5,
            total_users: 6,
            progress_trend: [{ label: '2026-09', value: 75 }],
            projects_by_status: [{ label: 'in_progress', value: 2, tone: 'info' }],
            assets_by_status: [{ label: 'operational', value: 4, tone: 'success' }],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )

    const stats = await getAdminStats()

    expect(stats.delayedProjects).toBe(1)
    expect(stats.operationalFacilities).toBe(1)
    expect(stats.progressTrend).toEqual([{ label: '2026-09', value: 75 }])
    expect(stats.progressTrend[0]).not.toHaveProperty('planned')
    expect(stats.projectsByStatus[0]).toMatchObject({ label: 'قيد التنفيذ', value: 2 })
  })
})
