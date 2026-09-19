import type {
  DocumentCategory,
  Facility,
  Incident,
  ProjectDocument,
  SecurityAlert,
  Severity,
} from '@/types'
import {
  apiRequest,
  downloadProtectedFile,
  fetchAllPages,
  saveDownloadedFile,
  unsupported,
} from './client'
import {
  alertFromDto,
  incidentFromDto,
  type EvidenceDto,
  type IncidentActionDto,
  type IncidentNoteDto,
  type IncidentDto,
  type SecurityAlertDto,
} from './adapters/security'

async function linkedIncidentIds(): Promise<Map<string, string>> {
  const incidents = await fetchAllPages<IncidentDto>('/security/incidents/')
  return new Map(
    incidents
      .filter((incident): incident is IncidentDto & { alert_id: string } =>
        Boolean(incident.alert_id),
      )
      .map((incident) => [incident.alert_id, incident.id]),
  )
}

export async function listAlerts(): Promise<SecurityAlert[]> {
  const [alerts, linked] = await Promise.all([
    fetchAllPages<SecurityAlertDto>('/security/alerts/'),
    linkedIncidentIds(),
  ])
  return alerts.map((alert) => alertFromDto(alert, linked.get(alert.id) ?? null))
}

export async function getAlert(id: string): Promise<SecurityAlert> {
  const [alert, linked] = await Promise.all([
    apiRequest<SecurityAlertDto>(`/security/alerts/${id}/`),
    linkedIncidentIds(),
  ])
  return alertFromDto(alert, linked.get(id) ?? null)
}

export async function setAlertStatus(id: string, _status: 'reviewed'): Promise<SecurityAlert> {
  const dto = await apiRequest<SecurityAlertDto>(`/security/alerts/${id}/review/`, {
    method: 'POST',
    body: { notes: '' },
  })
  return alertFromDto(dto)
}

export async function dismissAlert(id: string, reason: string): Promise<SecurityAlert> {
  const dto = await apiRequest<SecurityAlertDto>(`/security/alerts/${id}/dismiss/`, {
    method: 'POST',
    body: { reason },
  })
  return alertFromDto(dto)
}

export async function downloadAlertSnapshot(id: string): Promise<void> {
  const file = await downloadProtectedFile(
    `/security/alerts/${id}/snapshot/`,
    `security-alert-${id}`,
  )
  saveDownloadedFile(file)
}

export interface IncidentInput {
  facilityId: string
  alertId: string | null
  type: Incident['type']
  description: string
  location: string
  severity: Severity
  assigneeId: string | null
}

async function hydrateIncident(dto: IncidentDto): Promise<Incident> {
  const [actions, evidence, notes] = await Promise.all([
    fetchAllPages<IncidentActionDto>(`/security/incidents/${dto.id}/actions/`),
    fetchAllPages<EvidenceDto>(`/security/incidents/${dto.id}/evidence/`),
    fetchAllPages<IncidentNoteDto>(`/security/incidents/${dto.id}/notes/`),
  ])
  return incidentFromDto(dto, actions, evidence, notes)
}

export async function listIncidents(): Promise<Incident[]> {
  const incidents = await fetchAllPages<IncidentDto>('/security/incidents/')
  return incidents.map((incident) => incidentFromDto(incident))
}

export async function getIncident(id: string): Promise<Incident> {
  const incident = await apiRequest<IncidentDto>(`/security/incidents/${id}/`)
  return hydrateIncident(incident)
}

export async function createIncident(input: IncidentInput): Promise<Incident> {
  const body = input.alertId
    ? {
        incident_type: input.type,
        description: input.description,
        assigned_to: input.assigneeId,
      }
    : {
        facility: input.facilityId,
        incident_type: input.type,
        description: input.description,
        location: input.location,
        severity_level: input.severity,
        assigned_to: input.assigneeId,
      }
  const path = input.alertId
    ? `/security/alerts/${input.alertId}/convert-to-incident/`
    : '/security/incidents/'
  const incident = await apiRequest<IncidentDto>(path, { method: 'POST', body })
  return hydrateIncident(incident)
}

export async function updateIncident(
  id: string,
  input: Partial<Pick<Incident, 'description' | 'location' | 'severity' | 'status' | 'assigneeId'>>,
): Promise<Incident> {
  if (input.status === 'investigation') return startIncidentInvestigation(id, input.assigneeId)
  unsupported(
    'تعديل بيانات الحادث مباشرة غير مدعوم من واجهة الخلفية الحالية؛ استخدم إجراءات دورة الحياة المتاحة.',
  )
}

export async function startIncidentInvestigation(
  id: string,
  assignedTo: string | null = null,
): Promise<Incident> {
  const incident = await apiRequest<IncidentDto>(`/security/incidents/${id}/start-investigation/`, {
    method: 'POST',
    body: { assigned_to: assignedTo },
  })
  return hydrateIncident(incident)
}

export async function addIncidentNote(
  id: string,
  body: string,
  _authorId: string,
): Promise<Incident> {
  await apiRequest<IncidentNoteDto>(`/security/incidents/${id}/notes/`, {
    method: 'POST',
    body: { body },
  })
  return getIncident(id)
}

export interface SecurityCamera {
  id: string
  name: string
  code: string
  zone: string
  facilityId: string
  status: 'online' | 'offline' | 'degraded' | 'maintenance'
  online: boolean
  streamAvailable: boolean
  lastSeenAt: string | null
}

interface CameraDto {
  id: string
  facility_id: string
  code: string
  name: string
  zone: string
  status: SecurityCamera['status']
  last_seen_at: string | null
  stream_available: boolean
}

export async function listCameras(): Promise<SecurityCamera[]> {
  const cameras = await fetchAllPages<CameraDto>('/security/cameras/')
  return cameras.map((camera) => ({
    id: camera.id,
    name: camera.name,
    code: camera.code,
    zone: camera.zone,
    facilityId: camera.facility_id,
    status: camera.status,
    online: camera.status === 'online',
    streamAvailable: camera.stream_available,
    lastSeenAt: camera.last_seen_at,
  }))
}

export interface SecurityFacility {
  id: string
  name: string
  type: Facility['type']
  location: string
  status: Facility['status']
  operation_start_date?: string | null
}

export async function listSecurityFacilities(): Promise<SecurityFacility[]> {
  return fetchAllPages<SecurityFacility>('/security/facilities/')
}

export async function getSecurityFacility(id: string): Promise<SecurityFacility> {
  return apiRequest<SecurityFacility>(`/security/facilities/${id}/`)
}

interface SafetyDocumentDto {
  id: string
  facility_id: string
  title: string
  category: DocumentCategory
  original_file_name: string
  mime_type: string
  file_size: number
  uploaded_by_id: string
  uploaded_at: string
  download_url: string | null
}

const safetyDocumentFromDto = (document: SafetyDocumentDto): ProjectDocument => {
  const extension = document.original_file_name.split('.').pop()?.toLowerCase()
  const fileType =
    extension === 'docx' || extension === 'xlsx' || extension === 'jpg' ? extension : 'pdf'
  return {
    id: document.id,
    projectId: document.facility_id,
    name: document.title,
    category: document.category,
    fileType,
    sizeKb: Math.ceil(document.file_size / 1024),
    uploadedById: document.uploaded_by_id,
    uploadedAt: document.uploaded_at,
    originalFileName: document.original_file_name,
    downloadUrl: document.download_url,
  }
}

export async function listSafetyDocuments(): Promise<ProjectDocument[]> {
  return (await fetchAllPages<SafetyDocumentDto>('/security/documents/')).map(safetyDocumentFromDto)
}

export async function createSafetyDocument(input: {
  facilityId: string
  name: string
  category: DocumentCategory
  file: File
}): Promise<ProjectDocument> {
  const form = new FormData()
  form.append('facility', input.facilityId)
  form.append('title', input.name)
  form.append('category', input.category)
  form.append('file', input.file)
  return safetyDocumentFromDto(
    await apiRequest<SafetyDocumentDto>('/security/documents/', { method: 'POST', body: form }),
  )
}

export async function downloadSafetyDocument(id: string, filename: string): Promise<void> {
  saveDownloadedFile(await downloadProtectedFile(`/security/documents/${id}/download/`, filename))
}

export async function deleteSafetyDocument(id: string): Promise<void> {
  await apiRequest(`/security/documents/${id}/`, { method: 'DELETE' })
}

export async function addIncidentAction(id: string, label: string): Promise<Incident> {
  await apiRequest<IncidentActionDto>(`/security/incidents/${id}/actions/`, {
    method: 'POST',
    body: { action_taken: label, notes: '' },
  })
  return getIncident(id)
}

export async function toggleIncidentAction(id: string, actionId: string): Promise<Incident> {
  const incident = await getIncident(id)
  const action = incident.actions.find((candidate) => candidate.id === actionId)
  if (!action) throw new Error('The response action no longer exists.')
  await apiRequest(`/security/incidents/${id}/actions/${actionId}/completion/`, {
    method: 'PATCH',
    body: { completed: !action.done },
  })
  return getIncident(id)
}

export async function addIncidentEvidence(id: string, file: File): Promise<Incident> {
  const body = new FormData()
  body.append('file', file)
  await apiRequest<EvidenceDto>(`/security/incidents/${id}/evidence/`, {
    method: 'POST',
    body,
  })
  return getIncident(id)
}

export async function downloadIncidentEvidence(
  evidenceId: string,
  filename: string,
): Promise<void> {
  const file = await downloadProtectedFile(`/security/evidence/${evidenceId}/download/`, filename)
  saveDownloadedFile(file)
}

export async function escalateToOperations(
  id: string,
  operationsManagerId?: string,
): Promise<Incident> {
  if (!operationsManagerId) {
    const users = await apiRequest<{ id: string }[]>('/security/assignees/?role=operations_manager')
    if (users.length !== 1) {
      throw new Error('Select an assigned operations manager before transferring this incident.')
    }
    operationsManagerId = users[0]?.id
  }
  const incident = await apiRequest<IncidentDto>(`/security/incidents/${id}/transfer/`, {
    method: 'POST',
    body: { assigned_to: operationsManagerId },
  })
  return hydrateIncident(incident)
}

export async function closeIncident(
  id: string,
  finalReport: string,
  _closedById: string,
): Promise<Incident> {
  const incident = await apiRequest<IncidentDto>(`/security/incidents/${id}/close/`, {
    method: 'POST',
    body: { final_report: finalReport },
  })
  return hydrateIncident(incident)
}
