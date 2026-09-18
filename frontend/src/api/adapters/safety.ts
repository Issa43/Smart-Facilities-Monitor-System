import type {
  HazardAlertLevel,
  HazardEvent,
  HazardProvider,
  HazardProviderStatus,
  HazardType,
  SafetyAction,
  SafetyActionProposal,
  SafetyAlert,
  SafetyAlertStatus,
  SafetyAssetSummary,
  SafetyDecisionType,
  SafetyOpenProposal,
  SafetyProposalStatus,
  SafetyMonitoringCoverage,
  SafetyPersonSummary,
  SafetyProjectStatus,
  SafetyProjectSummary,
  SafetyRecommendedAction,
  SafetyWorkflowAction,
  Severity,
} from '@/types'
import { SAFETY_WORKFLOW_ACTIONS } from '@/types'

/* DTOs use the exact Phase 3 serializer field names (snake_case). */

export interface SafetyUserSummaryDto {
  id: string
  full_name: string
}

export interface SafetyProjectSummaryDto {
  id: string
  name: string
  location: string
  status: SafetyProjectStatus
  facility_id: string | null
}

export interface HazardEventDto {
  id: string
  provider: HazardProvider
  provider_event_id: string
  hazard_type: HazardType
  title: string
  alert_level: HazardAlertLevel | null
  provider_severity: string
  magnitude: string | null
  depth_km: string | null
  latitude: string
  longitude: string
  radius_km: string | null
  occurred_at: string
  valid_from: string | null
  valid_until: string | null
  provider_updated_at: string
  provider_status: HazardProviderStatus
  revision: number
  source_url: string
  created_at: string
  updated_at: string
}

export interface SafetyAlertDto {
  id: string
  project: SafetyProjectSummaryDto
  hazard_event: HazardEventDto
  hazard_type: HazardType
  severity: Severity
  status: SafetyAlertStatus
  distance_km: string
  project_latitude: string
  project_longitude: string
  rule_code: string
  policy_version: number
  recommended_action: SafetyRecommendedAction
  decision: SafetyAction | null
  decision_notes: string
  acknowledged_by: SafetyUserSummaryDto | null
  acknowledged_at: string | null
  decided_by: SafetyUserSummaryDto | null
  decided_at: string | null
  resolution_notes: string
  resolved_by: SafetyUserSummaryDto | null
  resolved_at: string | null
  hazard_withdrawn_at: string | null
  escalated_at: string | null
  available_actions: string[]
  /* Optional in the type so older fixtures and any pre-workflow response
     still parse; the adapter treats an absent field as "nothing to do". */
  available_proposal_types?: string[]
  open_proposals?: SafetyOpenProposalDto[]
  created_at: string
  updated_at: string
}

export interface SafetyMonitoringCoverageDto {
  monitored_projects: number
  projects_with_coordinates: number
  projects_missing_coordinates: number
  alert_creation_enabled: boolean
}

const personFromDto = (dto: SafetyUserSummaryDto | null): SafetyPersonSummary | null =>
  dto ? { id: dto.id, fullName: dto.full_name } : null

const projectFromDto = (dto: SafetyProjectSummaryDto): SafetyProjectSummary => ({
  id: dto.id,
  name: dto.name,
  location: dto.location,
  status: dto.status,
  facilityId: dto.facility_id,
})

const WORKFLOW_ACTIONS = new Set<string>(SAFETY_WORKFLOW_ACTIONS)
const DECISION_TYPES = new Set<string>(['worker_protection', 'asset_protection'])

export interface SafetyOpenProposalDto {
  id: string
  decision_type: string
  proposed_action: string
  proposal_notes: string
  effective_from: string | null
  effective_until: string | null
  worker_scope: string
  status: string
  proposed_by: SafetyUserSummaryDto
  proposed_at: string
  can_review: boolean
}

const openProposalFromDto = (dto: SafetyOpenProposalDto): SafetyOpenProposal => ({
  id: dto.id,
  decisionType: dto.decision_type as SafetyDecisionType,
  proposedAction: dto.proposed_action as SafetyAction,
  proposalNotes: dto.proposal_notes,
  effectiveFrom: dto.effective_from ?? null,
  effectiveUntil: dto.effective_until ?? null,
  workerScope: dto.worker_scope ?? '',
  status: dto.status as SafetyProposalStatus,
  proposedBy: { id: dto.proposed_by.id, fullName: dto.proposed_by.full_name },
  proposedAt: dto.proposed_at,
  canReview: dto.can_review === true,
})

/** Keep only workflow actions this client understands; unknown values are ignored. */
export function availableActionsFromDto(values: string[]): SafetyWorkflowAction[] {
  return values.filter((value): value is SafetyWorkflowAction => WORKFLOW_ACTIONS.has(value))
}

export const hazardEventFromDto = (dto: HazardEventDto): HazardEvent => ({
  id: dto.id,
  provider: dto.provider,
  providerEventId: dto.provider_event_id,
  hazardType: dto.hazard_type,
  title: dto.title,
  alertLevel: dto.alert_level,
  providerSeverity: dto.provider_severity,
  magnitude: dto.magnitude,
  depthKm: dto.depth_km,
  latitude: dto.latitude,
  longitude: dto.longitude,
  radiusKm: dto.radius_km,
  occurredAt: dto.occurred_at,
  validFrom: dto.valid_from,
  validUntil: dto.valid_until,
  providerUpdatedAt: dto.provider_updated_at,
  providerStatus: dto.provider_status,
  revision: dto.revision,
  sourceUrl: dto.source_url,
  createdAt: dto.created_at,
  updatedAt: dto.updated_at,
})

export const safetyAlertFromDto = (dto: SafetyAlertDto): SafetyAlert => ({
  id: dto.id,
  project: projectFromDto(dto.project),
  hazardEvent: hazardEventFromDto(dto.hazard_event),
  hazardType: dto.hazard_type,
  severity: dto.severity,
  status: dto.status,
  distanceKm: dto.distance_km,
  projectLatitude: dto.project_latitude,
  projectLongitude: dto.project_longitude,
  ruleCode: dto.rule_code,
  policyVersion: dto.policy_version,
  recommendedAction: dto.recommended_action,
  decision: dto.decision,
  decisionNotes: dto.decision_notes,
  acknowledgedBy: personFromDto(dto.acknowledged_by),
  acknowledgedAt: dto.acknowledged_at,
  decidedBy: personFromDto(dto.decided_by),
  decidedAt: dto.decided_at,
  resolutionNotes: dto.resolution_notes,
  resolvedBy: personFromDto(dto.resolved_by),
  resolvedAt: dto.resolved_at,
  hazardWithdrawnAt: dto.hazard_withdrawn_at,
  escalatedAt: dto.escalated_at,
  availableActions: availableActionsFromDto(dto.available_actions),
  availableProposalTypes: (dto.available_proposal_types ?? []).filter(
    (value): value is SafetyDecisionType => DECISION_TYPES.has(value),
  ),
  openProposals: (dto.open_proposals ?? []).map(openProposalFromDto),
  createdAt: dto.created_at,
  updatedAt: dto.updated_at,
})

export const coverageFromDto = (dto: SafetyMonitoringCoverageDto): SafetyMonitoringCoverage => ({
  monitoredProjects: dto.monitored_projects,
  projectsWithCoordinates: dto.projects_with_coordinates,
  projectsMissingCoordinates: dto.projects_missing_coordinates,
  alertCreationEnabled: dto.alert_creation_enabled,
})

/* ------------------------------------------------------------------ *
 * Human decision workflow
 * ------------------------------------------------------------------ */

export interface SafetyAssetSummaryDto {
  id: string
  name: string
  asset_type: string
  current_status: string
}

export interface SafetyActionProposalDto {
  id: string
  alert: SafetyAlertDto
  decision_type: string
  proposed_action: string
  proposal_notes: string
  effective_from: string | null
  effective_until: string | null
  worker_scope: string
  status: string
  affected_assets: SafetyAssetSummaryDto[]
  proposed_by: SafetyUserSummaryDto
  proposed_at: string
  reviewed_by: SafetyUserSummaryDto | null
  reviewed_at: string | null
  review_notes: string
  can_review: boolean
  created_at: string
  updated_at: string
}

const assetFromDto = (dto: SafetyAssetSummaryDto): SafetyAssetSummary => ({
  id: dto.id,
  name: dto.name,
  assetType: dto.asset_type,
  currentStatus: dto.current_status,
})

export const safetyProposalFromDto = (dto: SafetyActionProposalDto): SafetyActionProposal => ({
  id: dto.id,
  alert: safetyAlertFromDto(dto.alert),
  decisionType: dto.decision_type as SafetyDecisionType,
  proposedAction: dto.proposed_action as SafetyAction,
  proposalNotes: dto.proposal_notes,
  effectiveFrom: dto.effective_from ?? null,
  effectiveUntil: dto.effective_until ?? null,
  workerScope: dto.worker_scope ?? '',
  status: dto.status as SafetyProposalStatus,
  affectedAssets: (dto.affected_assets ?? []).map(assetFromDto),
  proposedBy: {
    id: dto.proposed_by.id,
    fullName: dto.proposed_by.full_name,
  },
  proposedAt: dto.proposed_at,
  reviewedBy: personFromDto(dto.reviewed_by),
  reviewedAt: dto.reviewed_at,
  reviewNotes: dto.review_notes,
  // Never inferred from a role in the client: the server decides.
  canReview: dto.can_review === true,
  createdAt: dto.created_at,
  updatedAt: dto.updated_at,
})
