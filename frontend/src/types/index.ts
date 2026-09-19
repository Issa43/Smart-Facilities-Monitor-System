/**
 * The domain model for the whole platform.
 *
 * Every enum ships with two maps beside it:
 *   *_LABELS  the Arabic string shown to the user
 *   *_TONE    which visual tone (badge colour) it renders with
 *
 * Keeping these next to the type is what makes a status render identically
 * on a dashboard, a table row and a detail page without anyone re-deciding.
 */

/** The five visual tones every status in the system maps onto. */
export type Tone = 'success' | 'warning' | 'critical' | 'info' | 'neutral'

/* ==========================================================================
   Roles & users
   ========================================================================== */

export type Role =
  'super_admin' | 'construction_manager' | 'operations_manager' | 'security_officer'

export const ROLES: Role[] = [
  'super_admin',
  'construction_manager',
  'operations_manager',
  'security_officer',
]

export const ROLE_LABELS: Record<Role, string> = {
  super_admin: 'المدير العام',
  construction_manager: 'مدير الإنشاءات',
  operations_manager: 'مدير التشغيل',
  security_officer: 'مسؤول الأمن',
}

export const ROLE_DESCRIPTIONS: Record<Role, string> = {
  super_admin: 'إنشاء المشاريع، إدارة المستخدمين والصلاحيات، ومتابعة كل مراحل دورة الحياة',
  construction_manager: 'إدارة مراحل التنفيذ والمواد والجودة حتى تسليم المشروع',
  operations_manager: 'إدارة الأصول وأعمال الصيانة والأعطال بعد التشغيل',
  security_officer: 'متابعة التنبيهات الأمنية وتوثيق الحوادث وإغلاقها',
}

export type AccountStatus = 'active' | 'inactive' | 'suspended'

export const ACCOUNT_STATUS_LABELS: Record<AccountStatus, string> = {
  active: 'نشط',
  inactive: 'مؤرشف',
  suspended: 'موقوف',
}

export const ACCOUNT_STATUS_TONE: Record<AccountStatus, Tone> = {
  active: 'success',
  inactive: 'neutral',
  suspended: 'neutral',
}

export interface User {
  id: string
  fullName: string
  email: string
  phone: string
  username: string
  role: Role
  status: AccountStatus
  profileImageUrl?: string | null
  /** Two Arabic letters shown in the avatar circle. */
  initials: string
  lastLoginAt: string | null
  createdAt: string
  /**
   * True when the user is referenced by projects, work orders or incidents.
   * The requirements forbid deleting such a user — only deactivating them.
   */
  hasOperationalRecords: boolean | null
}

/* ==========================================================================
   Projects & construction
   ========================================================================== */

export type FacilityType =
  | 'commercial'
  | 'residential'
  | 'industrial'
  | 'healthcare'
  | 'education'
  | 'government'
  | 'mixed_use'
  | 'other'

export const FACILITY_TYPE_LABELS: Record<FacilityType, string> = {
  commercial: 'منشأة تجارية',
  residential: 'مجمع سكني',
  industrial: 'منشأة صناعية',
  healthcare: 'منشأة صحية',
  education: 'منشأة تعليمية',
  government: 'منشأة حكومية',
  mixed_use: 'منشأة متعددة الاستخدام',
  other: 'نوع آخر',
}

export type ProjectStatus = 'planning' | 'in_progress' | 'completed' | 'operational'

export const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  planning: 'قيد التخطيط',
  in_progress: 'قيد التنفيذ',
  completed: 'مكتمل',
  operational: 'قيد التشغيل',
}

export const PROJECT_STATUS_TONE: Record<ProjectStatus, Tone> = {
  planning: 'neutral',
  in_progress: 'info',
  completed: 'success',
  operational: 'success',
}

export interface Project {
  id: string
  name: string
  facilityType: FacilityType
  description: string
  location: string
  /** Exact point chosen on the map. Null until someone picks one; the
   *  Safety domain matches hazards on these fields. */
  latitude: number | null
  longitude: number | null
  startDate: string
  expectedEndDate: string
  status: ProjectStatus
  imageUrl: string | null
  constructionManagerId: string
  constructionManagerName?: string
  progressPercent: number
  currentStageName: string
  updatedAt: string
}

export type StageStatus =
  'not_started' | 'in_progress' | 'completed' | 'rejected' | 'needs_modification'

export const STAGE_STATUS_LABELS: Record<StageStatus, string> = {
  not_started: 'لم تبدأ',
  in_progress: 'قيد التنفيذ',
  completed: 'مكتملة',
  rejected: 'مرفوضة',
  needs_modification: 'تحتاج إلى تعديل',
}

export const STAGE_STATUS_TONE: Record<StageStatus, Tone> = {
  not_started: 'neutral',
  in_progress: 'info',
  completed: 'success',
  rejected: 'critical',
  needs_modification: 'warning',
}

export type Priority = 'low' | 'medium' | 'high' | 'critical'

export const PRIORITY_LABELS: Record<Priority, string> = {
  low: 'منخفضة',
  medium: 'متوسطة',
  high: 'عالية',
  critical: 'حرجة',
}

export const PRIORITY_TONE: Record<Priority, Tone> = {
  low: 'neutral',
  medium: 'info',
  high: 'warning',
  critical: 'critical',
}

export interface Stage {
  id: string
  projectId: string
  name: string
  description: string
  startDate: string
  expectedEndDate: string
  progressPercent: number
  priority: Priority
  status: StageStatus
  /** Set when a manager approves or rejects the stage during quality review. */
  reviewNote: string | null
  updatedAt: string
}

/** One entry in a stage's execution log — the audit trail of progress updates. */
export interface StageUpdate {
  id: string
  stageId: string
  progressPercent: number
  completedWork: string
  note: string
  photoCount: number
  authorId: string
  createdAt: string
}

/* ==========================================================================
   Materials
   ========================================================================== */

export interface Material {
  id: string
  projectId: string
  name: string
  unit: string
  requiredQty: number
  usedQty: number
  /** Derived: requiredQty - usedQty. Stored so the API stays the shape a REST endpoint would return. */
  remainingQty: number
  minStockThreshold: number
}

export type MaterialRequestStatus = 'pending' | 'approved' | 'rejected' | 'delivered'

export const MATERIAL_REQUEST_STATUS_LABELS: Record<MaterialRequestStatus, string> = {
  pending: 'قيد المعالجة',
  approved: 'معتمد',
  rejected: 'مرفوض',
  delivered: 'تم التوريد',
}

export const MATERIAL_REQUEST_STATUS_TONE: Record<MaterialRequestStatus, Tone> = {
  pending: 'warning',
  approved: 'info',
  rejected: 'critical',
  delivered: 'success',
}

export interface MaterialRequest {
  id: string
  projectId: string
  projectName: string
  materialId: string
  materialName: string
  requestedQty: number
  unit: string
  reason: string
  priority: Priority
  status: MaterialRequestStatus
  requestedById: string
  requestedByName: string
  createdAt: string
}

/* ==========================================================================
   Quality, documentation
   ========================================================================== */

export type InspectionResult = 'passed' | 'passed_with_notes' | 'failed'

export const INSPECTION_RESULT_LABELS: Record<InspectionResult, string> = {
  passed: 'مطابق',
  passed_with_notes: 'مطابق مع ملاحظات',
  failed: 'غير مطابق',
}

export const INSPECTION_RESULT_TONE: Record<InspectionResult, Tone> = {
  passed: 'success',
  passed_with_notes: 'warning',
  failed: 'critical',
}

export interface QualityInspection {
  id: string
  projectId: string
  stageId: string
  title: string
  inspectorId: string
  inspectorName?: string
  score: number
  result: InspectionResult
  notes: string
  inspectedAt: string
}

export interface DailyReport {
  id: string
  projectId: string
  title: string
  summary: string
  progressPercent: number
  workforceCount: number
  photoCount: number
  authorId: string
  authorName?: string
  reportDate: string
}

export type DocumentCategory = 'drawing' | 'contract' | 'permit' | 'report' | 'policy' | 'procedure'

export const DOCUMENT_CATEGORY_LABELS: Record<DocumentCategory, string> = {
  drawing: 'مخططات',
  contract: 'عقود',
  permit: 'تصاريح',
  report: 'تقارير',
  policy: 'سياسات',
  procedure: 'إجراءات',
}

export interface ProjectDocument {
  id: string
  projectId: string | null
  name: string
  category: DocumentCategory
  fileType: 'pdf' | 'dwg' | 'xlsx' | 'docx' | 'jpg'
  sizeKb: number
  uploadedById: string
  uploadedByName?: string
  uploadedAt: string
  originalFileName?: string
  downloadUrl?: string | null
}

export interface SitePhoto {
  id: string
  projectId: string
  stageId: string | null
  caption: string
  /** A CSS gradient stands in for a real image — no binary assets in the repo. */
  gradient: string
  takenAt: string
}

/* ==========================================================================
   Facilities & assets (post-handover)
   ========================================================================== */

export type FacilityStatus = 'operational' | 'under_maintenance' | 'decommissioned'

export const FACILITY_STATUS_LABELS: Record<FacilityStatus, string> = {
  operational: 'تشغيل كامل',
  under_maintenance: 'تحت الصيانة',
  decommissioned: 'خارج الخدمة نهائياً',
}

export const FACILITY_STATUS_TONE: Record<FacilityStatus, Tone> = {
  operational: 'success',
  under_maintenance: 'info',
  decommissioned: 'neutral',
}

export interface Facility {
  id: string
  /** The project this facility was handed over from. */
  projectId: string
  name: string
  type: FacilityType
  location: string
  operationStartDate: string
  status: FacilityStatus
  assetCount: number
  /** The current backend does not expose an uptime metric. */
  uptimePercent: number | null
  /** Facility-assignment lookup is not exposed by the current backend. */
  operationsManagerId: string | null
}

export type AssetStatus = 'operational' | 'under_maintenance' | 'out_of_service'

export const ASSET_STATUS_LABELS: Record<AssetStatus, string> = {
  operational: 'يعمل',
  under_maintenance: 'تحت الصيانة',
  out_of_service: 'خارج الخدمة',
}

export const ASSET_STATUS_TONE: Record<AssetStatus, Tone> = {
  operational: 'success',
  under_maintenance: 'info',
  out_of_service: 'critical',
}

export type AssetCategory = string

export const ASSET_CATEGORY_LABELS: Record<AssetCategory, string> = {
  hvac: 'تكييف وتهوية',
  electrical: 'أنظمة كهربائية',
  plumbing: 'أنظمة سباكة',
  fire_safety: 'مكافحة حريق',
  elevator: 'مصاعد',
  security: 'أنظمة أمنية',
}

export function assetCategoryLabel(value: string): string {
  return ASSET_CATEGORY_LABELS[value] ?? value
}

export interface Asset {
  id: string
  facilityId: string
  name: string
  assetType?: string
  category: AssetCategory
  locationInFacility: string
  serialNumber: string
  installDate: string
  commissionDate: string | null
  status: AssetStatus
  notes: string
  manufacturer?: string
  model?: string
  remainingUsefulLife?: number | null
  createdById?: string
  createdAt?: string
  /** 0-100. Drives the asset health centre. */
  healthScore: number
  lastMaintenanceAt: string | null
  faultCount: number
  updatedAt: string
}

/* ==========================================================================
   Maintenance & faults
   ========================================================================== */

export type MaintenanceType = 'preventive' | 'corrective' | 'emergency'

export const MAINTENANCE_TYPE_LABELS: Record<MaintenanceType, string> = {
  preventive: 'صيانة وقائية',
  corrective: 'صيانة تصحيحية',
  emergency: 'صيانة طارئة',
}

export type WorkOrderStatus =
  'open' | 'assigned' | 'in_progress' | 'completed' | 'closed' | 'cancelled'

export const WORK_ORDER_STATUS_LABELS: Record<WorkOrderStatus, string> = {
  open: 'مفتوح',
  assigned: 'مُسند',
  in_progress: 'قيد التنفيذ',
  completed: 'مكتمل',
  closed: 'مغلق',
  cancelled: 'ملغي',
}

export const WORK_ORDER_STATUS_TONE: Record<WorkOrderStatus, Tone> = {
  open: 'warning',
  assigned: 'info',
  in_progress: 'info',
  completed: 'success',
  closed: 'success',
  cancelled: 'neutral',
}

export interface WorkOrderTask {
  id: string
  sequence?: number
  label: string
  done: boolean
  completedAt?: string | null
  completedById?: string | null
}

export interface WorkOrder {
  id: string
  /** Human-readable reference, e.g. WO-2026-0184. */
  reference: string
  assetId: string
  assetType?: string
  facilityId: string
  maintenanceType: MaintenanceType
  reason: string
  description: string
  priority: Priority
  status: WorkOrderStatus
  scheduledDate: string
  completedDate: string | null
  assignedToId: string | null
  notes: string
  tasks: WorkOrderTask[]
  cancelledAt?: string | null
  cancelledById?: string | null
  cancellationReason?: string
  createdAt: string
}

export type FaultStatus = 'reported' | 'investigating' | 'resolved' | 'closed'

export const FAULT_STATUS_LABELS: Record<FaultStatus, string> = {
  reported: 'تم الإبلاغ',
  investigating: 'قيد الفحص',
  resolved: 'تم الإصلاح',
  closed: 'مغلق',
}

export const FAULT_STATUS_TONE: Record<FaultStatus, Tone> = {
  reported: 'warning',
  investigating: 'info',
  resolved: 'success',
  closed: 'success',
}

export type Severity = 'low' | 'medium' | 'high' | 'critical'

export const SEVERITY_LABELS: Record<Severity, string> = {
  low: 'منخفضة',
  medium: 'متوسطة',
  high: 'عالية',
  critical: 'حرجة',
}

export const SEVERITY_TONE: Record<Severity, Tone> = {
  low: 'neutral',
  medium: 'info',
  high: 'warning',
  critical: 'critical',
}

export interface Fault {
  id: string
  reference: string
  assetId: string
  facilityId: string
  faultType: string
  description: string
  severity: Severity
  rootCause: string | null
  resolution?: string | null
  status: FaultStatus
  assignedToId: string | null
  discoveredAt: string
  resolvedAt: string | null
}

/* ==========================================================================
   Security — alerts & incidents
   ========================================================================== */

export type AlertType =
  | 'fire'
  | 'smoke'
  | 'intrusion'
  | 'motion'
  | 'unauthorized_person'
  | 'emergency'
  | 'vehicle'
  | 'tamper'

export const ALERT_TYPE_LABELS: Record<AlertType, string> = {
  fire: 'إنذار حريق',
  smoke: 'إنذار دخان',
  intrusion: 'محاولة اقتحام',
  motion: 'حركة مشبوهة',
  unauthorized_person: 'شخص غير مصرح له',
  emergency: 'حالة طوارئ',
  vehicle: 'مركبة',
  tamper: 'عبث بالكاميرا',
}

export const ALERT_TYPE_TONE: Record<AlertType, Tone> = {
  fire: 'critical',
  smoke: 'warning',
  intrusion: 'critical',
  motion: 'info',
  unauthorized_person: 'warning',
  emergency: 'critical',
  vehicle: 'info',
  tamper: 'critical',
}

export function alertTypeLabel(value: string): string {
  return ALERT_TYPE_LABELS[value as AlertType] ?? value
}

export function alertTypeTone(value: string): Tone {
  return ALERT_TYPE_TONE[value as AlertType] ?? 'neutral'
}

export type AlertStatus = 'new' | 'reviewed' | 'converted' | 'dismissed'

export const ALERT_STATUS_LABELS: Record<AlertStatus, string> = {
  new: 'جديد',
  reviewed: 'تمت المراجعة',
  converted: 'تم التحويل إلى حادث',
  dismissed: 'إنذار كاذب',
}

export const ALERT_STATUS_TONE: Record<AlertStatus, Tone> = {
  new: 'critical',
  reviewed: 'info',
  converted: 'warning',
  dismissed: 'neutral',
}

export interface SecurityAlert {
  id: string
  reference: string
  facilityId: string
  type: AlertType
  location: string
  severity: Severity
  status: AlertStatus
  /** Which camera / sensor / system raised it. */
  source: string
  detectedAt: string
  confidence?: number | null
  cameraEventId?: string | null
  eventType?: CameraEventType | null
  cameraId?: string | null
  cameraCode?: string | null
  roiId?: string | null
  roiIdentifier?: string | null
  snapshotAvailable?: boolean
  /** Set once the alert has been escalated into an incident. */
  incidentId: string | null
}

export type CameraEventType =
  | 'fire_alert'
  | 'smoke_alert'
  | 'intrusion_alert'
  | 'vehicle_entry'
  | 'vehicle_exit'
  | 'tamper_alert'

export const CAMERA_EVENT_TYPE_LABELS: Record<CameraEventType, string> = {
  fire_alert: 'إنذار حريق',
  smoke_alert: 'إنذار دخان',
  intrusion_alert: 'دخول غير مصرح به',
  vehicle_entry: 'دخول مركبة',
  vehicle_exit: 'خروج مركبة',
  tamper_alert: 'عبث بالكاميرا',
}

export interface PixelPoint {
  x: number
  y: number
}

export interface BoundingBox {
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface CameraEvent {
  id: string
  eventType: CameraEventType
  cameraId: string
  cameraCode: string
  facilityId: string
  facilityName: string
  roiId: string | null
  roiIdentifier: string | null
  trackId: string | null
  confidence: number | null
  objectClass: string | null
  detectedAt: string
  confirmedAt: string | null
  durationSeconds: number | null
  bbox: BoundingBox | null
  bboxPlate: BoundingBox | null
  bboxVehicle: BoundingBox | null
  crossingCentroid: PixelPoint | null
  enteredRoiAt: string | null
  timeRestricted: boolean | null
  plateNumber: string | null
  plateConfidence: number | null
  ocrConfidence: number | null
  vehicleType: 'car' | 'truck' | 'van' | 'bus' | 'motorcycle' | null
  vehicleConfidence: number | null
  direction: 'entry' | 'exit' | null
  authorized: boolean | null
  tamperType: 'camera_covered' | 'camera_moved' | 'signal_lost' | 'out_of_focus' | null
  status: AlertStatus | 'recorded'
  securityAlertId: string | null
  snapshotAvailable: boolean
  snapshotDownloadUrl: string | null
  createdAt: string
  updatedAt: string
}

export interface CameraRoi {
  id: string
  cameraId: string
  identifier: string
  name: string
  polygon: PixelPoint[]
  isActive: boolean
}

export interface RestrictedZoneSchedule {
  id: string
  roiId: string
  cameraId: string
  alwaysRestricted: boolean
  fromTime: string | null
  toTime: string | null
  daysOfWeek: number[]
  timezoneName: string
  crossesMidnight: boolean
  isActive: boolean
}

export interface VirtualLine {
  id: string
  cameraId: string
  lineStart: PixelPoint
  lineEnd: PixelPoint
  isActive: boolean
}

export interface AuthorizedVehicle {
  id: string
  plateNumber: string
  responsibleName: string
  expiresOn: string | null
  currentlyAuthorized: boolean
  isActive: boolean
}

export type CameraAiModelIdentifier = 'fire_smoke' | 'intrusion' | 'anpr' | 'tamper'

export interface CameraAiModel {
  id: string
  cameraId: string
  modelIdentifier: CameraAiModelIdentifier
  isActive: boolean
  updatedAt: string
}

export type IncidentStatus = 'open' | 'investigation' | 'transferred' | 'closed'

export const INCIDENT_STATUS_LABELS: Record<IncidentStatus, string> = {
  open: 'مفتوح',
  investigation: 'قيد التحقيق',
  transferred: 'محول إلى التشغيل',
  closed: 'مغلق',
}

export const INCIDENT_STATUS_TONE: Record<IncidentStatus, Tone> = {
  open: 'critical',
  investigation: 'warning',
  transferred: 'warning',
  closed: 'success',
}

export interface IncidentAction {
  id: string
  label: string
  done: boolean
  takenAt: string | null
}

export interface IncidentNote {
  id: string
  body: string
  authorId: string
  createdAt: string
}

export interface Incident {
  id: string
  /** Human-readable reference, e.g. INC-2026-0042. */
  reference: string
  facilityId: string
  alertId: string | null
  type: string
  description: string
  location: string
  severity: Severity
  status: IncidentStatus
  assigneeId: string | null
  notes: IncidentNote[]
  actions: IncidentAction[]
  /** Gradients standing in for uploaded evidence photos. */
  evidence: {
    id: string
    caption: string
    gradient: string | null
    originalFileName?: string
    downloadUrl?: string
  }[]
  /** Set when the security officer escalates to the operations manager. */
  escalatedToOperations: boolean
  createdAt: string
  closedAt: string | null
  closedById: string | null
  finalReport: string | null
}

/* ==========================================================================
   Cross-cutting
   ========================================================================== */

export type NotificationCategory =
  'project' | 'material' | 'maintenance' | 'security' | 'safety' | 'system'

export const NOTIFICATION_CATEGORY_LABELS: Record<NotificationCategory, string> = {
  project: 'المشاريع',
  material: 'المواد',
  maintenance: 'الصيانة',
  security: 'الأمن',
  safety: 'السلامة',
  system: 'النظام',
}

export interface AppNotification {
  id: string
  title: string
  body: string
  category: NotificationCategory
  tone: Tone
  read: boolean
  /** Which roles should see it. */
  audience: Role[]
  href: string | null
  createdAt: string
}

export interface AuditLogEntry {
  id: string
  actorId: string
  actorName?: string
  action: string
  entity: string
  entityRef: string
  ip: string
  createdAt: string
}

export type ReportKind =
  | 'projects'
  | 'construction'
  | 'materials'
  | 'assets'
  | 'maintenance'
  | 'faults'
  | 'incidents'
  | 'users'
  | 'alerts'
  | 'response'
  | 'operational_performance'

export const REPORT_KIND_LABELS: Record<ReportKind, string> = {
  projects: 'تقرير المشاريع',
  construction: 'تقرير الإنشاءات',
  materials: 'تقرير المواد',
  assets: 'تقرير الأصول',
  maintenance: 'تقرير الصيانة',
  faults: 'تقرير الأعطال',
  incidents: 'تقرير الحوادث',
  users: 'تقرير المستخدمين',
  alerts: 'تقرير التنبيهات',
  response: 'تقرير الاستجابة',
  operational_performance: 'تقرير الأداء التشغيلي',
}

export interface GeneratedReport {
  id: string
  kind: ReportKind
  title: string
  format: 'pdf' | 'excel'
  periodLabel: string
  generatedById: string
  generatedAt: string
  sizeKb: number | null
  status?: 'queued' | 'processing' | 'completed' | 'failed'
  failureDetails?: string | null
  downloadAvailable?: boolean
}

export * from './safety'
