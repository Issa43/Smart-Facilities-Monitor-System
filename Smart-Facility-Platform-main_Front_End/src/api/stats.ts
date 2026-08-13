import type { Tone } from '@/types'
import { sortByTone } from '@/lib/tone'
import { delay } from './client'
import { getDb } from './db'

/**
 * Dashboard aggregates.
 *
 * These are computed here rather than in the pages for two reasons: a real
 * backend would expose them as summary endpoints (one request instead of six),
 * and it keeps four dashboards from each inventing their own arithmetic for
 * "open work orders" and disagreeing about the number.
 */

export interface TrendPoint {
  label: string
  value: number
  planned?: number
}

export interface DistributionSlice {
  label: string
  value: number
  tone: Tone
}

/**
 * Drops empty slices and applies the canonical severity order.
 *
 * Taking DistributionSlice[] as a parameter is what gives each call site's
 * array literal a contextual type, so `tone: 'info'` narrows to Tone instead of
 * widening to string.
 */
function distribution(slices: DistributionSlice[]): DistributionSlice[] {
  return sortByTone(slices.filter((slice) => slice.value > 0))
}

/* ==========================================================================
   Super Admin — platform-wide
   ========================================================================== */

export interface AdminStats {
  totalProjects: number
  activeProjects: number
  overallProgress: number
  operationalFacilities: number
  totalAssets: number
  assetHealth: number
  openWorkOrders: number
  overdueWorkOrders: number
  openIncidents: number
  criticalAlerts: number
  activeUsers: number
  totalUsers: number
  progressTrend: TrendPoint[]
  projectsByStatus: DistributionSlice[]
  assetsByStatus: DistributionSlice[]
}

export async function getAdminStats(): Promise<AdminStats> {
  await delay()
  const db = getDb()

  const activeProjects = db.projects.filter(
    (p) => p.status === 'in_progress' || p.status === 'planning',
  )
  const construction = db.projects.filter((p) => p.status !== 'operational')
  const overallProgress =
    construction.length === 0
      ? 100
      : Math.round(
          construction.reduce((sum, p) => sum + p.progressPercent, 0) / construction.length,
        )

  const assetHealth =
    db.assets.length === 0
      ? 100
      : Math.round(db.assets.reduce((sum, a) => sum + a.healthScore, 0) / db.assets.length)

  const openWorkOrders = db.workOrders.filter(
    (w) => w.status === 'open' || w.status === 'in_progress',
  )
  const now = Date.now()

  return {
    totalProjects: db.projects.length,
    activeProjects: activeProjects.length,
    overallProgress,
    operationalFacilities: db.facilities.length,
    totalAssets: db.assets.length,
    assetHealth,
    openWorkOrders: openWorkOrders.length,
    overdueWorkOrders: openWorkOrders.filter((w) => new Date(w.scheduledDate).getTime() < now)
      .length,
    openIncidents: db.incidents.filter((i) => i.status !== 'closed').length,
    criticalAlerts: db.alerts.filter((a) => a.severity === 'critical' && a.status === 'new').length,
    activeUsers: db.users.filter((u) => u.status === 'active').length,
    totalUsers: db.users.length,
    progressTrend: buildProgressTrend(overallProgress),
    projectsByStatus: distribution([
      {
        label: 'قيد التنفيذ',
        value: db.projects.filter((p) => p.status === 'in_progress').length,
        tone: 'info',
      },
      {
        label: 'قيد التشغيل',
        value: db.projects.filter((p) => p.status === 'operational').length,
        tone: 'success',
      },
      {
        label: 'قيد التخطيط',
        value: db.projects.filter((p) => p.status === 'planning').length,
        tone: 'neutral',
      },
      {
        label: 'متوقف مؤقتاً',
        value: db.projects.filter((p) => p.status === 'on_hold').length,
        tone: 'warning',
      },
    ]),
    assetsByStatus: distribution([
      {
        label: 'يعمل',
        value: db.assets.filter((a) => a.status === 'operational').length,
        tone: 'success',
      },
      {
        label: 'يحتاج صيانة',
        value: db.assets.filter((a) => a.status === 'needs_maintenance').length,
        tone: 'warning',
      },
      {
        label: 'تحت الصيانة',
        value: db.assets.filter((a) => a.status === 'under_maintenance').length,
        tone: 'info',
      },
      {
        label: 'خارج الخدمة',
        value: db.assets.filter((a) => a.status === 'out_of_service').length,
        tone: 'critical',
      },
    ]),
  }
}

/* ==========================================================================
   Construction Manager
   ========================================================================== */

export interface ConstructionStats {
  myProjects: number
  averageProgress: number
  activeStages: number
  stagesUnderReview: number
  pendingRequests: number
  lowStockMaterials: number
  qualityScore: number
  failedInspections: number
  delayedStages: number
  progressTrend: TrendPoint[]
  stagesByStatus: DistributionSlice[]
}

export async function getConstructionStats(managerId: string): Promise<ConstructionStats> {
  await delay()
  const db = getDb()

  const myProjects = db.projects.filter(
    (p) => p.constructionManagerId === managerId && p.status !== 'operational',
  )
  const projectIds = new Set(myProjects.map((p) => p.id))
  const myStages = db.stages.filter((s) => projectIds.has(s.projectId))
  const myRequests = db.materialRequests.filter((r) => projectIds.has(r.projectId))
  const myMaterials = db.materials.filter((m) => projectIds.has(m.projectId))
  const myInspections = db.qualityInspections.filter((i) => projectIds.has(i.projectId))

  const averageProgress =
    myProjects.length === 0
      ? 0
      : Math.round(myProjects.reduce((sum, p) => sum + p.progressPercent, 0) / myProjects.length)

  const qualityScore =
    myInspections.length === 0
      ? 0
      : Math.round(myInspections.reduce((sum, i) => sum + i.score, 0) / myInspections.length)

  const now = Date.now()

  return {
    myProjects: myProjects.length,
    averageProgress,
    activeStages: myStages.filter((s) => s.status === 'in_progress').length,
    stagesUnderReview: myStages.filter((s) => s.status === 'under_review').length,
    pendingRequests: myRequests.filter((r) => r.status === 'pending').length,
    lowStockMaterials: myMaterials.filter((m) => m.remainingQty < m.minStockThreshold).length,
    qualityScore,
    failedInspections: myInspections.filter((i) => i.result === 'failed').length,
    delayedStages: myStages.filter(
      (s) => s.status !== 'completed' && new Date(s.expectedEndDate).getTime() < now,
    ).length,
    progressTrend: buildProgressTrend(averageProgress),
    stagesByStatus: distribution([
      {
        label: 'مكتملة',
        value: myStages.filter((s) => s.status === 'completed').length,
        tone: 'success',
      },
      {
        label: 'قيد التنفيذ',
        value: myStages.filter((s) => s.status === 'in_progress').length,
        tone: 'info',
      },
      {
        label: 'قيد المراجعة',
        value: myStages.filter((s) => s.status === 'under_review').length,
        tone: 'warning',
      },
      {
        label: 'لم تبدأ',
        value: myStages.filter((s) => s.status === 'not_started').length,
        tone: 'neutral',
      },
      {
        label: 'مرفوضة',
        value: myStages.filter((s) => s.status === 'rejected').length,
        tone: 'critical',
      },
    ]),
  }
}

/* ==========================================================================
   Operations Manager
   ========================================================================== */

export interface OperationsStats {
  facilities: number
  totalAssets: number
  assetHealth: number
  operationalAssets: number
  outOfServiceAssets: number
  openWorkOrders: number
  overdueWorkOrders: number
  completedThisMonth: number
  openFaults: number
  criticalFaults: number
  averageUptime: number
  maintenanceTrend: TrendPoint[]
  assetsByStatus: DistributionSlice[]
}

export async function getOperationsStats(): Promise<OperationsStats> {
  await delay()
  const db = getDb()

  const assetHealth =
    db.assets.length === 0
      ? 100
      : Math.round(db.assets.reduce((sum, a) => sum + a.healthScore, 0) / db.assets.length)

  const openWorkOrders = db.workOrders.filter(
    (w) => w.status === 'open' || w.status === 'in_progress',
  )
  const now = Date.now()
  const monthAgo = now - 30 * 86_400_000

  const averageUptime =
    db.facilities.length === 0
      ? 100
      : Math.round(
          (db.facilities.reduce((sum, f) => sum + f.uptimePercent, 0) / db.facilities.length) * 10,
        ) / 10

  return {
    facilities: db.facilities.length,
    totalAssets: db.assets.length,
    assetHealth,
    operationalAssets: db.assets.filter((a) => a.status === 'operational').length,
    outOfServiceAssets: db.assets.filter((a) => a.status === 'out_of_service').length,
    openWorkOrders: openWorkOrders.length,
    overdueWorkOrders: openWorkOrders.filter((w) => new Date(w.scheduledDate).getTime() < now)
      .length,
    completedThisMonth: db.workOrders.filter(
      (w) => w.completedDate && new Date(w.completedDate).getTime() > monthAgo,
    ).length,
    openFaults: db.faults.filter((f) => f.status !== 'resolved').length,
    criticalFaults: db.faults.filter((f) => f.status !== 'resolved' && f.severity === 'critical')
      .length,
    averageUptime,
    maintenanceTrend: buildMaintenanceTrend(),
    assetsByStatus: distribution([
      {
        label: 'يعمل',
        value: db.assets.filter((a) => a.status === 'operational').length,
        tone: 'success',
      },
      {
        label: 'يحتاج صيانة',
        value: db.assets.filter((a) => a.status === 'needs_maintenance').length,
        tone: 'warning',
      },
      {
        label: 'تحت الصيانة',
        value: db.assets.filter((a) => a.status === 'under_maintenance').length,
        tone: 'info',
      },
      {
        label: 'خارج الخدمة',
        value: db.assets.filter((a) => a.status === 'out_of_service').length,
        tone: 'critical',
      },
    ]),
  }
}

/* ==========================================================================
   Security Officer
   ========================================================================== */

export interface SecurityStats {
  newAlerts: number
  criticalAlerts: number
  alertsToday: number
  falseAlarmRate: number
  openIncidents: number
  closedIncidents: number
  incidentsThisMonth: number
  averageResponseMinutes: number
  alertTrend: TrendPoint[]
  alertsByType: DistributionSlice[]
  incidentsBySeverity: DistributionSlice[]
}

export async function getSecurityStats(): Promise<SecurityStats> {
  await delay()
  const db = getDb()

  const dayAgo = Date.now() - 86_400_000
  const monthAgo = Date.now() - 30 * 86_400_000
  const dismissed = db.alerts.filter((a) => a.status === 'dismissed').length

  return {
    newAlerts: db.alerts.filter((a) => a.status === 'new').length,
    criticalAlerts: db.alerts.filter((a) => a.severity === 'critical' && a.status === 'new').length,
    alertsToday: db.alerts.filter((a) => new Date(a.detectedAt).getTime() > dayAgo).length,
    falseAlarmRate: db.alerts.length === 0 ? 0 : Math.round((dismissed / db.alerts.length) * 100),
    openIncidents: db.incidents.filter((i) => i.status !== 'closed').length,
    closedIncidents: db.incidents.filter((i) => i.status === 'closed').length,
    incidentsThisMonth: db.incidents.filter((i) => new Date(i.createdAt).getTime() > monthAgo)
      .length,
    averageResponseMinutes: 14,
    alertTrend: buildAlertTrend(),
    alertsByType: distribution([
      {
        label: 'اقتحام',
        value: db.alerts.filter((a) => a.type === 'intrusion').length,
        tone: 'critical',
      },
      { label: 'حريق', value: db.alerts.filter((a) => a.type === 'fire').length, tone: 'critical' },
      { label: 'دخان', value: db.alerts.filter((a) => a.type === 'smoke').length, tone: 'warning' },
      { label: 'حركة', value: db.alerts.filter((a) => a.type === 'motion').length, tone: 'info' },
      {
        label: 'دخول غير مصرح',
        value: db.alerts.filter((a) => a.type === 'unauthorized_person').length,
        tone: 'warning',
      },
      {
        label: 'طوارئ',
        value: db.alerts.filter((a) => a.type === 'emergency').length,
        tone: 'critical',
      },
    ]),
    incidentsBySeverity: distribution([
      {
        label: 'حرجة',
        value: db.incidents.filter((i) => i.severity === 'critical').length,
        tone: 'critical',
      },
      {
        label: 'عالية',
        value: db.incidents.filter((i) => i.severity === 'high').length,
        tone: 'warning',
      },
      {
        label: 'متوسطة',
        value: db.incidents.filter((i) => i.severity === 'medium').length,
        tone: 'info',
      },
      {
        label: 'منخفضة',
        value: db.incidents.filter((i) => i.severity === 'low').length,
        tone: 'neutral',
      },
    ]),
  }
}

/* ==========================================================================
   Trend builders
   ========================================================================== */

const MONTH_LABELS = new Intl.DateTimeFormat('ar-SA-u-ca-gregory-nu-latn', { month: 'short' })

function lastSixMonths(): string[] {
  const labels: string[] = []
  for (let i = 5; i >= 0; i--) {
    const d = new Date()
    d.setMonth(d.getMonth() - i, 1)
    labels.push(MONTH_LABELS.format(d))
  }
  return labels
}

/** Back-fills six months of history ending at the real current value. */
function buildProgressTrend(current: number): TrendPoint[] {
  const labels = lastSixMonths()
  const start = Math.max(0, current - 34)
  return labels.map((label, i) => {
    const value = Math.round(start + ((current - start) * i) / (labels.length - 1))
    return {
      label,
      value,
      planned: Math.min(
        100,
        Math.round(start + 7 + (i * (current - start + 12)) / (labels.length - 1)),
      ),
    }
  })
}

function buildMaintenanceTrend(): TrendPoint[] {
  const completed = [14, 18, 16, 21, 19, 24]
  return lastSixMonths().map((label, i) => ({ label, value: completed[i] ?? 0 }))
}

function buildAlertTrend(): TrendPoint[] {
  const counts = [22, 18, 27, 19, 24, 16]
  return lastSixMonths().map((label, i) => ({ label, value: counts[i] ?? 0 }))
}
