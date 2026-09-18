/* ==========================================================================
   External safety alerts (الإنذارات والسلامة)

   Enum values mirror the backend OpenAPI contract exactly:
   SafetyAlertStatusEnum, SafetyActionEnum, SafetyRecommendedActionEnum,
   HazardTypeEnum, ProviderEnum, AlertLevelEnum, ProviderStatusEnum.
   Severity reuses the shared `Severity` type (identical value set).
   ========================================================================== */

import type { Severity, Tone } from './index'

export type SafetyAlertStatus = 'new' | 'acknowledged' | 'actioned' | 'closed' | 'dismissed'

export type SafetyAction =
  | 'suspend_outdoor_work'
  | 'delay_shift'
  | 'modify_working_hours'
  | 'increase_precautions'
  | 'inspect_site'
  | 'monitor'
  | 'other'

/** The system never recommends `other`; it is a human-only decision. */
export type SafetyRecommendedAction = Exclude<SafetyAction, 'other'>

export type SafetyWorkflowAction = 'acknowledge' | 'decide' | 'dismiss' | 'close'

export type HazardType =
  | 'earthquake'
  | 'tropical_cyclone'
  | 'flood'
  | 'volcano'
  | 'wildfire'
  | 'extreme_heat'
  | 'extreme_cold'
  | 'heavy_snow'
  | 'high_wind'
  | 'heavy_rain'
  | 'dust_storm'

export type HazardProvider = 'usgs' | 'gdacs' | 'mhews'
export type HazardAlertLevel = 'green' | 'orange' | 'red'
export type HazardProviderStatus = 'active' | 'withdrawn' | 'expired'
export type SafetyProjectStatus = 'planning' | 'in_progress' | 'completed' | 'operational'

export interface SafetyPersonSummary {
  id: string
  fullName: string
}

export interface SafetyProjectSummary {
  id: string
  name: string
  location: string
  status: SafetyProjectStatus
  facilityId: string | null
}

export interface HazardEvent {
  id: string
  provider: HazardProvider
  providerEventId: string
  hazardType: HazardType
  title: string
  alertLevel: HazardAlertLevel | null
  providerSeverity: string
  /** Decimal strings from the API are kept as strings to avoid precision loss. */
  magnitude: string | null
  depthKm: string | null
  latitude: string
  longitude: string
  radiusKm: string | null
  occurredAt: string
  validFrom: string | null
  validUntil: string | null
  providerUpdatedAt: string
  providerStatus: HazardProviderStatus
  revision: number
  sourceUrl: string
  createdAt: string
  updatedAt: string
}

export interface SafetyAlert {
  id: string
  project: SafetyProjectSummary
  hazardEvent: HazardEvent
  hazardType: HazardType
  severity: Severity
  status: SafetyAlertStatus
  distanceKm: string
  projectLatitude: string
  projectLongitude: string
  ruleCode: string
  policyVersion: number
  recommendedAction: SafetyRecommendedAction
  decision: SafetyAction | null
  decisionNotes: string
  acknowledgedBy: SafetyPersonSummary | null
  acknowledgedAt: string | null
  decidedBy: SafetyPersonSummary | null
  decidedAt: string | null
  resolutionNotes: string
  resolvedBy: SafetyPersonSummary | null
  resolvedAt: string | null
  hazardWithdrawnAt: string | null
  escalatedAt: string | null
  /** Server-calculated; the only source of which workflow controls to show. */
  availableActions: SafetyWorkflowAction[]
  /** Server-calculated: which protective actions this viewer may propose. */
  availableProposalTypes: SafetyDecisionType[]
  /** Proposals still awaiting a General Manager ruling. */
  openProposals: SafetyOpenProposal[]
  createdAt: string
  updatedAt: string
}

/** An open proposal as carried inline on its alert (no nested alert). */
export interface SafetyOpenProposal {
  id: string
  decisionType: SafetyDecisionType
  proposedAction: SafetyAction
  proposalNotes: string
  effectiveFrom: string | null
  effectiveUntil: string | null
  workerScope: string
  status: SafetyProposalStatus
  proposedBy: SafetyPersonSummary
  proposedAt: string
  canReview: boolean
}

export interface SafetyMonitoringCoverage {
  monitoredProjects: number
  projectsWithCoordinates: number
  projectsMissingCoordinates: number
  alertCreationEnabled: boolean
}

export interface SafetyPage<T> {
  items: T[]
  count: number
  page: number
  totalPages: number
}

export type SafetyAlertOrdering =
  'created_at' | '-created_at' | 'updated_at' | '-updated_at' | 'distance_km' | '-distance_km'

export type HazardEventOrdering =
  | 'occurred_at'
  | '-occurred_at'
  | 'provider_updated_at'
  | '-provider_updated_at'
  | 'created_at'
  | '-created_at'

/** Exactly the Phase 3 alert filter contract; no other query names are sent. */
export interface SafetyAlertFilters {
  page?: number
  project?: string
  severity?: Severity
  status?: SafetyAlertStatus
  hazardType?: HazardType
  provider?: HazardProvider
  hazardWithdrawn?: boolean
  createdAfter?: string
  createdBefore?: string
  search?: string
  ordering?: SafetyAlertOrdering
}

export interface HazardEventFilters {
  page?: number
  provider?: HazardProvider
  hazardType?: HazardType
  alertLevel?: HazardAlertLevel
  providerStatus?: HazardProviderStatus
  project?: string
  occurredAfter?: string
  occurredBefore?: string
  search?: string
  ordering?: HazardEventOrdering
}

export interface SafetyDecisionInput {
  decision: SafetyAction
  notes?: string
}

export const SAFETY_ALERT_STATUS_LABELS: Record<SafetyAlertStatus, string> = {
  new: 'جديد',
  acknowledged: 'تم الإقرار',
  actioned: 'تم اتخاذ قرار',
  closed: 'مغلق',
  dismissed: 'مستبعد',
}

export const SAFETY_ALERT_STATUS_TONE: Record<SafetyAlertStatus, Tone> = {
  new: 'critical',
  acknowledged: 'warning',
  actioned: 'info',
  closed: 'success',
  dismissed: 'neutral',
}

export const SAFETY_ACTION_LABELS: Record<SafetyAction, string> = {
  suspend_outdoor_work: 'إيقاف الأعمال الخارجية مؤقتاً',
  delay_shift: 'تأجيل الوردية',
  modify_working_hours: 'تعديل ساعات العمل',
  increase_precautions: 'رفع إجراءات السلامة',
  inspect_site: 'فحص الموقع',
  monitor: 'المتابعة والمراقبة',
  other: 'إجراء آخر (مع ملاحظات)',
}

/** Ordered exactly as the backend SafetyActionEnum. */
export const SAFETY_ACTIONS: SafetyAction[] = [
  'suspend_outdoor_work',
  'delay_shift',
  'modify_working_hours',
  'increase_precautions',
  'inspect_site',
  'monitor',
  'other',
]

/** The decision the backend workflow rejects without notes. */
export const SAFETY_DECISION_REQUIRING_NOTES: SafetyAction = 'other'
export const SAFETY_NOTES_MAX_LENGTH = 2000

export const SAFETY_WORKFLOW_ACTIONS: SafetyWorkflowAction[] = [
  'acknowledge',
  'decide',
  'dismiss',
  'close',
]

export const SAFETY_WORKFLOW_ACTION_LABELS: Record<SafetyWorkflowAction, string> = {
  acknowledge: 'إقرار الاطلاع',
  decide: 'تسجيل القرار',
  dismiss: 'استبعاد الإنذار',
  close: 'إغلاق الإنذار',
}

export const HAZARD_TYPE_LABELS: Record<HazardType, string> = {
  earthquake: 'زلزال',
  tropical_cyclone: 'إعصار مداري',
  flood: 'فيضان',
  volcano: 'نشاط بركاني',
  wildfire: 'حريق غابات',
  extreme_heat: 'حرارة شديدة',
  extreme_cold: 'برودة شديدة',
  heavy_snow: 'تساقط كثيف للثلوج',
  high_wind: 'رياح شديدة',
  heavy_rain: 'أمطار غزيرة',
  dust_storm: 'عاصفة ترابية أو رملية',
}

export const HAZARD_PROVIDER_LABELS: Record<HazardProvider, string> = {
  usgs: 'USGS',
  gdacs: 'GDACS',
  mhews: 'MHEWS',
}

export const HAZARD_ALERT_LEVEL_LABELS: Record<HazardAlertLevel, string> = {
  green: 'أخضر',
  orange: 'برتقالي',
  red: 'أحمر',
}

export const HAZARD_PROVIDER_STATUS_LABELS: Record<HazardProviderStatus, string> = {
  active: 'نشط لدى المصدر',
  withdrawn: 'سحبه المصدر',
  expired: 'منتهٍ لدى المصدر',
}

export const SAFETY_PROJECT_STATUS_LABELS: Record<SafetyProjectStatus, string> = {
  planning: 'قيد التخطيط',
  in_progress: 'قيد التنفيذ',
  completed: 'مكتمل',
  operational: 'تشغيلي',
}

export const SAFETY_ALERT_ORDERING_LABELS: Record<SafetyAlertOrdering, string> = {
  '-created_at': 'الأحدث أولاً',
  created_at: 'الأقدم أولاً',
  '-updated_at': 'آخر تحديث أولاً',
  updated_at: 'أقدم تحديث أولاً',
  distance_km: 'الأقرب مسافةً',
  '-distance_km': 'الأبعد مسافةً',
}

/* ------------------------------------------------------------------ *
 * Human decision workflow
 *
 * An external hazard is information. It becomes an instruction only when a
 * responsible manager proposes an action and the General Manager approves it.
 * The two kinds of proposal have different owners and different consequences,
 * so they are distinct values rather than one free-text decision.
 * ------------------------------------------------------------------ */

export type SafetyDecisionType = 'worker_protection' | 'asset_protection'
export type SafetyProposalStatus = 'pending_manager_review' | 'approved' | 'rejected'

export interface SafetyAssetSummary {
  id: string
  name: string
  assetType: string
  currentStatus: string
}

export interface SafetyActionProposal {
  id: string
  alert: SafetyAlert
  decisionType: SafetyDecisionType
  proposedAction: SafetyAction
  proposalNotes: string
  effectiveFrom: string | null
  effectiveUntil: string | null
  workerScope: string
  status: SafetyProposalStatus
  affectedAssets: SafetyAssetSummary[]
  proposedBy: SafetyPersonSummary
  proposedAt: string
  reviewedBy: SafetyPersonSummary | null
  reviewedAt: string | null
  reviewNotes: string
  /** Server-calculated. The only source of whether to show Approve/Reject. */
  canReview: boolean
  createdAt: string
  updatedAt: string
}

export interface SafetyProposalFilters {
  decisionType?: SafetyDecisionType
  status?: SafetyProposalStatus
  alert?: string
  project?: string
  mine?: boolean
  page?: number
  pageSize?: number
}

export interface SafetyProposalInput {
  decisionType: SafetyDecisionType
  proposedAction: SafetyAction
  notes: string
  assetIds?: string[]
  effectiveFrom?: string | null
  effectiveUntil?: string | null
  workerScope?: string
}

export const SAFETY_DECISION_TYPE_LABELS: Record<SafetyDecisionType, string> = {
  worker_protection: 'حماية العاملين',
  asset_protection: 'حماية الأصول',
}

export const SAFETY_PROPOSAL_STATUS_LABELS: Record<SafetyProposalStatus, string> = {
  pending_manager_review: 'بانتظار موافقة المدير العام',
  approved: 'معتمد',
  rejected: 'مرفوض',
}

export const SAFETY_PROPOSAL_STATUS_TONE: Record<SafetyProposalStatus, Tone> = {
  pending_manager_review: 'warning',
  approved: 'success',
  rejected: 'critical',
}
