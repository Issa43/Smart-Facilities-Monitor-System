import type { Tone } from '@/types'
import { apiRequest } from './client'

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

interface TrendDto {
  label: string
  value: number
  planned?: number
}

interface DistributionDto {
  label: string
  value: number
  tone: Tone
}

const labels: Record<string, string> = {
  planning: 'قيد التخطيط',
  in_progress: 'قيد التنفيذ',
  completed: 'مكتمل',
  operational: 'تشغيلي',
  not_started: 'لم تبدأ',
  rejected: 'مرفوضة',
  needs_modification: 'تحتاج إلى تعديل',
  under_maintenance: 'تحت الصيانة',
  out_of_service: 'خارج الخدمة',
  fire: 'حريق',
  smoke: 'دخان',
  intrusion: 'اقتحام',
  motion: 'حركة',
  unauthorized_person: 'دخول غير مصرح',
  emergency: 'طوارئ',
  vehicle: 'مركبة',
  critical: 'حرجة',
  high: 'عالية',
  medium: 'متوسطة',
  low: 'منخفضة',
}

const trend = (rows: TrendDto[]): TrendPoint[] => rows.map((row) => ({ ...row }))
const distribution = (rows: DistributionDto[]): DistributionSlice[] =>
  rows.map((row) => ({ ...row, label: labels[row.label] ?? row.label }))

export interface AdminStats {
  totalProjects: number
  activeProjects: number
  delayedProjects: number
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

interface AdminStatsDto {
  total_projects: number
  active_projects: number
  delayed_projects: number
  overall_progress: number
  operational_facilities: number
  total_assets: number
  asset_health: number
  open_work_orders: number
  overdue_work_orders: number
  open_incidents: number
  critical_alerts: number
  active_users: number
  total_users: number
  progress_trend: TrendDto[]
  projects_by_status: DistributionDto[]
  assets_by_status: DistributionDto[]
}

export async function getAdminStats(): Promise<AdminStats> {
  const dto = await apiRequest<AdminStatsDto>('/analytics/admin/')
  return {
    totalProjects: dto.total_projects,
    activeProjects: dto.active_projects,
    delayedProjects: dto.delayed_projects,
    overallProgress: dto.overall_progress,
    operationalFacilities: dto.operational_facilities,
    totalAssets: dto.total_assets,
    assetHealth: dto.asset_health,
    openWorkOrders: dto.open_work_orders,
    overdueWorkOrders: dto.overdue_work_orders,
    openIncidents: dto.open_incidents,
    criticalAlerts: dto.critical_alerts,
    activeUsers: dto.active_users,
    totalUsers: dto.total_users,
    progressTrend: trend(dto.progress_trend),
    projectsByStatus: distribution(dto.projects_by_status),
    assetsByStatus: distribution(dto.assets_by_status),
  }
}

export interface ConstructionStats {
  myProjects: number
  averageProgress: number
  activeStages: number
  stagesUnderReview: number
  pendingRequests: number
  lowStockMaterials: number
  qualityScore: number | null
  failedInspections: number
  delayedStages: number
  progressTrend: TrendPoint[]
  stagesByStatus: DistributionSlice[]
}

interface ConstructionStatsDto {
  my_projects: number
  average_progress: number
  active_stages: number
  stages_under_review: number
  pending_requests: number
  low_stock_materials: number
  quality_score: number | null
  failed_inspections: number
  delayed_stages: number
  progress_trend: TrendDto[]
  stages_by_status: DistributionDto[]
}

export async function getConstructionStats(_managerId: string): Promise<ConstructionStats> {
  const dto = await apiRequest<ConstructionStatsDto>('/analytics/construction/')
  return {
    myProjects: dto.my_projects,
    averageProgress: dto.average_progress,
    activeStages: dto.active_stages,
    stagesUnderReview: dto.stages_under_review,
    pendingRequests: dto.pending_requests,
    lowStockMaterials: dto.low_stock_materials,
    qualityScore: dto.quality_score,
    failedInspections: dto.failed_inspections,
    delayedStages: dto.delayed_stages,
    progressTrend: trend(dto.progress_trend),
    stagesByStatus: distribution(dto.stages_by_status),
  }
}

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
  averageUptime: number | null
  maintenanceTrend: TrendPoint[]
  assetsByStatus: DistributionSlice[]
}

interface OperationsStatsDto {
  facilities: number
  total_assets: number
  asset_health: number
  operational_assets: number
  out_of_service_assets: number
  open_work_orders: number
  overdue_work_orders: number
  completed_this_month: number
  open_faults: number
  critical_faults: number
  average_uptime: number | null
  maintenance_trend: TrendDto[]
  assets_by_status: DistributionDto[]
}

export async function getOperationsStats(): Promise<OperationsStats> {
  const dto = await apiRequest<OperationsStatsDto>('/analytics/operations/')
  return {
    facilities: dto.facilities,
    totalAssets: dto.total_assets,
    assetHealth: dto.asset_health,
    operationalAssets: dto.operational_assets,
    outOfServiceAssets: dto.out_of_service_assets,
    openWorkOrders: dto.open_work_orders,
    overdueWorkOrders: dto.overdue_work_orders,
    completedThisMonth: dto.completed_this_month,
    openFaults: dto.open_faults,
    criticalFaults: dto.critical_faults,
    averageUptime: dto.average_uptime,
    maintenanceTrend: trend(dto.maintenance_trend),
    assetsByStatus: distribution(dto.assets_by_status),
  }
}

export interface SecurityStats {
  newAlerts: number
  criticalAlerts: number
  alertsToday: number
  falseAlarmRate: number
  openIncidents: number
  closedIncidents: number
  incidentsThisMonth: number
  averageResponseMinutes: number | null
  alertTrend: TrendPoint[]
  alertsByType: DistributionSlice[]
  incidentsBySeverity: DistributionSlice[]
}

interface SecurityStatsDto {
  new_alerts: number
  critical_alerts: number
  alerts_today: number
  false_alarm_rate: number
  open_incidents: number
  closed_incidents: number
  incidents_this_month: number
  average_response_minutes: number | null
  alert_trend: TrendDto[]
  alerts_by_type: DistributionDto[]
  incidents_by_severity: DistributionDto[]
}

export async function getSecurityStats(): Promise<SecurityStats> {
  const dto = await apiRequest<SecurityStatsDto>('/analytics/security/')
  return {
    newAlerts: dto.new_alerts,
    criticalAlerts: dto.critical_alerts,
    alertsToday: dto.alerts_today,
    falseAlarmRate: dto.false_alarm_rate,
    openIncidents: dto.open_incidents,
    closedIncidents: dto.closed_incidents,
    incidentsThisMonth: dto.incidents_this_month,
    averageResponseMinutes: dto.average_response_minutes,
    alertTrend: trend(dto.alert_trend),
    alertsByType: distribution(dto.alerts_by_type),
    incidentsBySeverity: distribution(dto.incidents_by_severity),
  }
}
