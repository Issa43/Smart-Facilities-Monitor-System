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

export type AccountStatus = 'active' | 'suspended'

export const ACCOUNT_STATUS_LABELS: Record<AccountStatus, string> = {
  active: 'نشط',
  suspended: 'موقوف',
}

export const ACCOUNT_STATUS_TONE: Record<AccountStatus, Tone> = {
  active: 'success',
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
  /** Two Arabic letters shown in the avatar circle. */
  initials: string
  lastLoginAt: string | null
  createdAt: string
  /**
   * True when the user is referenced by projects, work orders or incidents.
   * The requirements forbid deleting such a user — only deactivating them.
   */
  hasOperationalRecords: boolean
}

/* ==========================================================================
   Projects & construction
   ========================================================================== */

export type FacilityType =
  'hospital' | 'school' | 'mall' | 'tower' | 'warehouse' | 'stadium' | 'residential'

export const FACILITY_TYPE_LABELS: Record<FacilityType, string> = {
  hospital: 'منشأة صحية',
  school: 'منشأة تعليمية',
  mall: 'مركز تجاري',
  tower: 'برج مكاتب',
  warehouse: 'مستودع لوجستي',
  stadium: 'منشأة رياضية',
  residential: 'مجمع سكني',
}

export type ProjectStatus = 'planning' | 'in_progress' | 'on_hold' | 'completed' | 'operational'

export const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  planning: 'قيد التخطيط',
  in_progress: 'قيد التنفيذ',
  on_hold: 'متوقف مؤقتاً',
  completed: 'مكتمل',
  operational: 'قيد التشغيل',
}

export const PROJECT_STATUS_TONE: Record<ProjectStatus, Tone> = {
  planning: 'neutral',
  in_progress: 'info',
  on_hold: 'warning',
  completed: 'success',
  operational: 'success',
}

export interface Project {
  id: string
  name: string
  facilityType: FacilityType
  description: string
  location: string
  startDate: string
  expectedEndDate: string
  status: ProjectStatus
  imageUrl: string | null
  constructionManagerId: string
  progressPercent: number
  currentStageName: string
  updatedAt: string
}

export type StageStatus = 'not_started' | 'in_progress' | 'under_review' | 'completed' | 'rejected'

export const STAGE_STATUS_LABELS: Record<StageStatus, string> = {
  not_started: 'لم تبدأ',
  in_progress: 'قيد التنفيذ',
  under_review: 'قيد المراجعة',
  completed: 'مكتملة',
  rejected: 'مرفوضة',
}

export const STAGE_STATUS_TONE: Record<StageStatus, Tone> = {
  not_started: 'neutral',
  in_progress: 'info',
  under_review: 'warning',
  completed: 'success',
  rejected: 'critical',
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
  materialName: string
  requestedQty: number
  unit: string
  reason: string
  priority: Priority
  status: MaterialRequestStatus
  requestedById: string
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
  uploadedAt: string
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

export type FacilityStatus = 'operational' | 'partial' | 'under_maintenance'

export const FACILITY_STATUS_LABELS: Record<FacilityStatus, string> = {
  operational: 'تشغيل كامل',
  partial: 'تشغيل جزئي',
  under_maintenance: 'تحت الصيانة',
}

export const FACILITY_STATUS_TONE: Record<FacilityStatus, Tone> = {
  operational: 'success',
  partial: 'warning',
  under_maintenance: 'info',
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
  uptimePercent: number
  operationsManagerId: string
}

export type AssetStatus =
  'operational' | 'needs_maintenance' | 'under_maintenance' | 'out_of_service'

export const ASSET_STATUS_LABELS: Record<AssetStatus, string> = {
  operational: 'يعمل',
  needs_maintenance: 'يحتاج صيانة',
  under_maintenance: 'تحت الصيانة',
  out_of_service: 'خارج الخدمة',
}

export const ASSET_STATUS_TONE: Record<AssetStatus, Tone> = {
  operational: 'success',
  needs_maintenance: 'warning',
  under_maintenance: 'info',
  out_of_service: 'critical',
}

export type AssetCategory =
  'hvac' | 'electrical' | 'plumbing' | 'fire_safety' | 'elevator' | 'security'

export const ASSET_CATEGORY_LABELS: Record<AssetCategory, string> = {
  hvac: 'تكييف وتهوية',
  electrical: 'أنظمة كهربائية',
  plumbing: 'أنظمة سباكة',
  fire_safety: 'مكافحة حريق',
  elevator: 'مصاعد',
  security: 'أنظمة أمنية',
}

export interface Asset {
  id: string
  facilityId: string
  name: string
  category: AssetCategory
  locationInFacility: string
  serialNumber: string
  installDate: string
  commissionDate: string
  status: AssetStatus
  notes: string
  /** 0-100. Drives the asset health centre. */
  healthScore: number
  lastMaintenanceAt: string | null
  faultCount: number
  updatedAt: string
}

/* ==========================================================================
   Maintenance & faults
   ========================================================================== */

export type MaintenanceType = 'preventive' | 'corrective'

export const MAINTENANCE_TYPE_LABELS: Record<MaintenanceType, string> = {
  preventive: 'صيانة وقائية',
  corrective: 'صيانة تصحيحية',
}

export type WorkOrderStatus = 'open' | 'in_progress' | 'completed' | 'cancelled'

export const WORK_ORDER_STATUS_LABELS: Record<WorkOrderStatus, string> = {
  open: 'مفتوح',
  in_progress: 'قيد التنفيذ',
  completed: 'مكتمل',
  cancelled: 'ملغي',
}

export const WORK_ORDER_STATUS_TONE: Record<WorkOrderStatus, Tone> = {
  open: 'warning',
  in_progress: 'info',
  completed: 'success',
  cancelled: 'neutral',
}

export interface WorkOrderTask {
  id: string
  label: string
  done: boolean
}

export interface WorkOrder {
  id: string
  /** Human-readable reference, e.g. WO-2026-0184. */
  reference: string
  assetId: string
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
  createdAt: string
}

export type FaultStatus = 'reported' | 'investigating' | 'repairing' | 'resolved'

export const FAULT_STATUS_LABELS: Record<FaultStatus, string> = {
  reported: 'تم الإبلاغ',
  investigating: 'قيد الفحص',
  repairing: 'قيد الإصلاح',
  resolved: 'تم الإصلاح',
}

export const FAULT_STATUS_TONE: Record<FaultStatus, Tone> = {
  reported: 'warning',
  investigating: 'info',
  repairing: 'info',
  resolved: 'success',
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
  status: FaultStatus
  assignedToId: string | null
  discoveredAt: string
  resolvedAt: string | null
}

/* ==========================================================================
   Security — alerts & incidents
   ========================================================================== */

export type AlertType =
  'fire' | 'smoke' | 'intrusion' | 'motion' | 'unauthorized_person' | 'emergency'

export const ALERT_TYPE_LABELS: Record<AlertType, string> = {
  fire: 'إنذار حريق',
  smoke: 'إنذار دخان',
  intrusion: 'محاولة اقتحام',
  motion: 'حركة مشبوهة',
  unauthorized_person: 'شخص غير مصرح له',
  emergency: 'حالة طوارئ',
}

export const ALERT_TYPE_TONE: Record<AlertType, Tone> = {
  fire: 'critical',
  smoke: 'warning',
  intrusion: 'critical',
  motion: 'info',
  unauthorized_person: 'warning',
  emergency: 'critical',
}

export type AlertStatus = 'new' | 'acknowledged' | 'escalated' | 'dismissed'

export const ALERT_STATUS_LABELS: Record<AlertStatus, string> = {
  new: 'جديد',
  acknowledged: 'تمت المراجعة',
  escalated: 'تم التصعيد',
  dismissed: 'إنذار كاذب',
}

export const ALERT_STATUS_TONE: Record<AlertStatus, Tone> = {
  new: 'critical',
  acknowledged: 'info',
  escalated: 'warning',
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
  /** Set once the alert has been escalated into an incident. */
  incidentId: string | null
}

export type IncidentStatus = 'new' | 'investigating' | 'action_required' | 'resolved' | 'closed'

export const INCIDENT_STATUS_LABELS: Record<IncidentStatus, string> = {
  new: 'جديد',
  investigating: 'قيد التحقيق',
  action_required: 'يتطلب إجراء',
  resolved: 'تمت المعالجة',
  closed: 'مغلق',
}

export const INCIDENT_STATUS_TONE: Record<IncidentStatus, Tone> = {
  new: 'critical',
  investigating: 'warning',
  action_required: 'warning',
  resolved: 'info',
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
  type: AlertType
  description: string
  location: string
  severity: Severity
  status: IncidentStatus
  assigneeId: string
  notes: IncidentNote[]
  actions: IncidentAction[]
  /** Gradients standing in for uploaded evidence photos. */
  evidence: { id: string; caption: string; gradient: string }[]
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

export type NotificationCategory = 'project' | 'material' | 'maintenance' | 'security' | 'system'

export const NOTIFICATION_CATEGORY_LABELS: Record<NotificationCategory, string> = {
  project: 'المشاريع',
  material: 'المواد',
  maintenance: 'الصيانة',
  security: 'الأمن',
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
  sizeKb: number
}
