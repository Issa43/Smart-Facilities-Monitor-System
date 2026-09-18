import type {
  AppNotification,
  Asset,
  AuditLogEntry,
  DailyReport,
  Facility,
  Fault,
  GeneratedReport,
  Incident,
  Material,
  MaterialRequest,
  Project,
  ProjectDocument,
  QualityInspection,
  SecurityAlert,
  SitePhoto,
  Stage,
  StageUpdate,
  User,
  WorkOrder,
} from '@/types'

import { users } from './users'
import { projects, stages, stageUpdates } from './projects'
import {
  dailyReports,
  documents,
  materialRequests,
  materials,
  qualityInspections,
  sitePhotos,
} from './construction'
import { assets, facilities, faults, workOrders } from './operations'
import { alerts, incidents } from './security'
import { auditLogs, generatedReports, notifications } from './system'

export { DEMO_USER_IDS } from './users'

/** The whole application's data, in one object. */
export interface Database {
  users: User[]
  projects: Project[]
  stages: Stage[]
  stageUpdates: StageUpdate[]
  materials: Material[]
  materialRequests: MaterialRequest[]
  qualityInspections: QualityInspection[]
  dailyReports: DailyReport[]
  documents: ProjectDocument[]
  sitePhotos: SitePhoto[]
  facilities: Facility[]
  assets: Asset[]
  workOrders: WorkOrder[]
  faults: Fault[]
  alerts: SecurityAlert[]
  incidents: Incident[]
  notifications: AppNotification[]
  auditLogs: AuditLogEntry[]
  generatedReports: GeneratedReport[]
}

/**
 * A fresh copy of the seed data. Called on first run and by "reset demo data".
 * structuredClone matters — without it, mutations would write through to the
 * imported fixture arrays and a reset would be a no-op.
 */
export function createSeedDatabase(): Database {
  return structuredClone({
    users,
    projects,
    stages,
    stageUpdates,
    materials,
    materialRequests,
    qualityInspections,
    dailyReports,
    documents,
    sitePhotos,
    facilities,
    assets,
    workOrders,
    faults,
    alerts,
    incidents,
    notifications,
    auditLogs,
    generatedReports,
  })
}
