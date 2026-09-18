import type {
  HazardEvent,
  HazardEventFilters,
  SafetyActionProposal,
  SafetyAlert,
  SafetyAlertFilters,
  SafetyDecisionInput,
  SafetyMonitoringCoverage,
  SafetyPage,
  SafetyProposalFilters,
  SafetyProposalInput,
} from '@/types'
import { apiRequest, type PaginatedResponse } from './client'
import {
  coverageFromDto,
  hazardEventFromDto,
  safetyAlertFromDto,
  safetyProposalFromDto,
  type HazardEventDto,
  type SafetyActionProposalDto,
  type SafetyAlertDto,
  type SafetyMonitoringCoverageDto,
} from './adapters/safety'

/**
 * Safety REST client. Every request goes through the shared `apiRequest`, so
 * JWT, refresh, and the standard error envelope are handled centrally. Only
 * the Phase 3 filter names are ever sent.
 */

function toPage<Dto, Model>(
  response: PaginatedResponse<Dto>,
  map: (dto: Dto) => Model,
): SafetyPage<Model> {
  return {
    items: response.results.map(map),
    count: response.count,
    page: response.current_page,
    totalPages: response.total_pages,
  }
}

function setIfPresent(params: URLSearchParams, name: string, value: string | undefined) {
  const trimmed = value?.trim()
  if (trimmed) params.set(name, trimmed)
}

const segment = (id: string) => encodeURIComponent(id)

export function safetyAlertQueryString(filters: SafetyAlertFilters = {}): string {
  const params = new URLSearchParams()
  if (filters.page && filters.page > 1) params.set('page', String(filters.page))
  setIfPresent(params, 'project', filters.project)
  setIfPresent(params, 'severity', filters.severity)
  setIfPresent(params, 'status', filters.status)
  setIfPresent(params, 'hazard_type', filters.hazardType)
  setIfPresent(params, 'provider', filters.provider)
  if (filters.hazardWithdrawn !== undefined) {
    params.set('hazard_withdrawn', filters.hazardWithdrawn ? 'true' : 'false')
  }
  setIfPresent(params, 'created_after', filters.createdAfter)
  setIfPresent(params, 'created_before', filters.createdBefore)
  setIfPresent(params, 'search', filters.search)
  setIfPresent(params, 'ordering', filters.ordering)
  return params.toString()
}

export function hazardEventQueryString(filters: HazardEventFilters = {}): string {
  const params = new URLSearchParams()
  if (filters.page && filters.page > 1) params.set('page', String(filters.page))
  setIfPresent(params, 'provider', filters.provider)
  setIfPresent(params, 'hazard_type', filters.hazardType)
  setIfPresent(params, 'alert_level', filters.alertLevel)
  setIfPresent(params, 'provider_status', filters.providerStatus)
  setIfPresent(params, 'project', filters.project)
  setIfPresent(params, 'occurred_after', filters.occurredAfter)
  setIfPresent(params, 'occurred_before', filters.occurredBefore)
  setIfPresent(params, 'search', filters.search)
  setIfPresent(params, 'ordering', filters.ordering)
  return params.toString()
}

const withQuery = (path: string, query: string) => (query ? `${path}?${query}` : path)

export async function listSafetyAlerts(
  filters: SafetyAlertFilters = {},
): Promise<SafetyPage<SafetyAlert>> {
  const response = await apiRequest<PaginatedResponse<SafetyAlertDto>>(
    withQuery('/safety/alerts/', safetyAlertQueryString(filters)),
  )
  return toPage(response, safetyAlertFromDto)
}

export async function getSafetyAlert(id: string): Promise<SafetyAlert> {
  return safetyAlertFromDto(await apiRequest<SafetyAlertDto>(`/safety/alerts/${segment(id)}/`))
}

async function postAction(
  id: string,
  action: string,
  body: Record<string, unknown>,
): Promise<SafetyAlert> {
  const dto = await apiRequest<SafetyAlertDto>(`/safety/alerts/${segment(id)}/${action}/`, {
    method: 'POST',
    body,
  })
  return safetyAlertFromDto(dto)
}

export function acknowledgeSafetyAlert(id: string): Promise<SafetyAlert> {
  return postAction(id, 'acknowledge', {})
}

export function decideSafetyAlert(id: string, input: SafetyDecisionInput): Promise<SafetyAlert> {
  const notes = input.notes?.trim()
  return postAction(
    id,
    'decide',
    notes ? { decision: input.decision, notes } : { decision: input.decision },
  )
}

export function dismissSafetyAlert(id: string, reason: string): Promise<SafetyAlert> {
  return postAction(id, 'dismiss', { reason: reason.trim() })
}

export function closeSafetyAlert(id: string, notes?: string): Promise<SafetyAlert> {
  const trimmed = notes?.trim()
  return postAction(id, 'close', trimmed ? { notes: trimmed } : {})
}

export async function listHazardEvents(
  filters: HazardEventFilters = {},
): Promise<SafetyPage<HazardEvent>> {
  const response = await apiRequest<PaginatedResponse<HazardEventDto>>(
    withQuery('/safety/hazard-events/', hazardEventQueryString(filters)),
  )
  return toPage(response, hazardEventFromDto)
}

export async function getHazardEvent(id: string): Promise<HazardEvent> {
  return hazardEventFromDto(
    await apiRequest<HazardEventDto>(`/safety/hazard-events/${segment(id)}/`),
  )
}

export async function getSafetyMonitoringCoverage(): Promise<SafetyMonitoringCoverage> {
  return coverageFromDto(
    await apiRequest<SafetyMonitoringCoverageDto>('/safety/monitoring-coverage/'),
  )
}

/* ------------------------------------------------------------------ *
 * Human decision workflow
 * ------------------------------------------------------------------ */

export function safetyProposalQueryString(filters: SafetyProposalFilters = {}): string {
  const params = new URLSearchParams()
  if (filters.page && filters.page > 1) params.set('page', String(filters.page))
  setIfPresent(params, 'decision_type', filters.decisionType)
  setIfPresent(params, 'status', filters.status)
  setIfPresent(params, 'alert', filters.alert)
  setIfPresent(params, 'project', filters.project)
  if (filters.mine !== undefined) params.set('mine', filters.mine ? 'true' : 'false')
  return params.toString()
}

export async function listSafetyProposals(
  filters: SafetyProposalFilters = {},
): Promise<SafetyPage<SafetyActionProposal>> {
  const response = await apiRequest<PaginatedResponse<SafetyActionProposalDto>>(
    withQuery('/safety/action-proposals/', safetyProposalQueryString(filters)),
  )
  return {
    items: response.results.map(safetyProposalFromDto),
    count: response.count,
    page: response.current_page,
    totalPages: response.total_pages,
  }
}

export async function getSafetyProposal(id: string): Promise<SafetyActionProposal> {
  return safetyProposalFromDto(
    await apiRequest<SafetyActionProposalDto>(`/safety/action-proposals/${segment(id)}/`),
  )
}

/** Propose a protective action on one alert. Dispatches nothing by itself. */
export async function createSafetyProposal(
  alertId: string,
  input: SafetyProposalInput,
): Promise<SafetyActionProposal> {
  const body: Record<string, unknown> = {
    decision_type: input.decisionType,
    proposed_action: input.proposedAction,
    notes: input.notes.trim(),
  }
  if (input.assetIds?.length) body.asset_ids = input.assetIds
  if (input.effectiveFrom) body.effective_from = input.effectiveFrom
  if (input.effectiveUntil) body.effective_until = input.effectiveUntil
  if (input.workerScope?.trim()) body.worker_scope = input.workerScope.trim()
  return safetyProposalFromDto(
    await apiRequest<SafetyActionProposalDto>(
      `/safety/alerts/${segment(alertId)}/proposals/`,
      { method: 'POST', body },
    ),
  )
}

async function postProposalRuling(
  id: string,
  verdict: 'approve' | 'reject',
  body: Record<string, unknown>,
): Promise<SafetyActionProposal> {
  return safetyProposalFromDto(
    await apiRequest<SafetyActionProposalDto>(
      `/safety/action-proposals/${segment(id)}/${verdict}/`,
      { method: 'POST', body },
    ),
  )
}

export function approveSafetyProposal(id: string, notes?: string): Promise<SafetyActionProposal> {
  const trimmed = notes?.trim()
  return postProposalRuling(id, 'approve', trimmed ? { notes: trimmed } : {})
}

export function rejectSafetyProposal(id: string, reason: string): Promise<SafetyActionProposal> {
  return postProposalRuling(id, 'reject', { reason: reason.trim() })
}
