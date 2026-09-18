import type { Incident, SecurityAlert } from '@/types'

export interface SecurityAlertDto {
  id: string
  facility_id: string
  facility_name: string
  alert_type: SecurityAlert['type']
  location: string
  severity_level: SecurityAlert['severity']
  source: string
  confidence_score: string | number | null
  camera_event_id: string | null
  event_type: SecurityAlert['eventType']
  camera_id: string | null
  camera_code: string | null
  roi_id: string | null
  roi_identifier: string | null
  snapshot_available: boolean
  snapshot_download_url: string | null
  status: SecurityAlert['status']
  is_false_positive: boolean
  reviewed_by_id: string | null
  review_notes: string
  created_by_id: string | null
  created_at: string
  updated_at: string
}

export interface IncidentDto {
  id: string
  incident_number: string
  facility_id: string
  facility_name: string
  alert_id: string | null
  incident_type: string
  description: string
  location: string
  severity_level: Incident['severity']
  assigned_to_id: string | null
  status: Incident['status']
  final_report: string | null
  closed_by_id: string | null
  closed_at: string | null
  created_by_id: string
  created_at: string
  updated_at: string
}

export interface IncidentActionDto {
  id: string
  incident_id: string
  action_taken: string
  notes: string
  taken_by_id: string
  taken_at: string
  completed_at: string | null
  completed_by_id: string | null
  created_by_id: string
  created_at: string
}

export interface IncidentNoteDto {
  id: string
  incident_id: string
  body: string
  author_id: string
  created_at: string
}

export interface EvidenceDto {
  id: string
  entity_type: 'incident' | 'incident_action'
  entity_id: string
  original_file_name: string
  file_type: string
  mime_type: string
  file_size: number
  created_by_id: string
  created_at: string
  download_url: string
}

function incidentType(value: string): Incident['type'] {
  return value.trim()
}

export function alertFromDto(
  dto: SecurityAlertDto,
  incidentId: string | null = null,
): SecurityAlert {
  return {
    id: dto.id,
    reference: dto.id,
    facilityId: dto.facility_id,
    type: dto.alert_type,
    location: dto.location,
    severity: dto.severity_level,
    status: dto.status,
    source: dto.source,
    detectedAt: dto.created_at,
    confidence: dto.confidence_score === null ? null : Number(dto.confidence_score),
    cameraEventId: dto.camera_event_id,
    eventType: dto.event_type,
    cameraId: dto.camera_id,
    cameraCode: dto.camera_code,
    roiId: dto.roi_id,
    roiIdentifier: dto.roi_identifier,
    snapshotAvailable: dto.snapshot_available,
    incidentId,
  }
}

export function actionFromDto(dto: IncidentActionDto): Incident['actions'][number] {
  return {
    id: dto.id,
    label: dto.notes ? `${dto.action_taken} — ${dto.notes}` : dto.action_taken,
    // Backend response actions are immutable facts; recording one means it occurred.
    done: dto.completed_at !== null,
    takenAt: dto.completed_at,
  }
}

export function evidenceFromDto(dto: EvidenceDto): Incident['evidence'][number] {
  return {
    id: dto.id,
    caption: dto.original_file_name,
    gradient: null,
    originalFileName: dto.original_file_name,
    downloadUrl: dto.download_url,
  }
}

export function incidentFromDto(
  dto: IncidentDto,
  actions: IncidentActionDto[] = [],
  evidence: EvidenceDto[] = [],
  notes: IncidentNoteDto[] = [],
): Incident {
  return {
    id: dto.id,
    reference: dto.incident_number,
    facilityId: dto.facility_id,
    alertId: dto.alert_id,
    type: incidentType(dto.incident_type),
    description: dto.description,
    location: dto.location,
    severity: dto.severity_level,
    status: dto.status,
    assigneeId: dto.assigned_to_id,
    notes: notes.map((note) => ({
      id: note.id,
      body: note.body,
      authorId: note.author_id,
      createdAt: note.created_at,
    })),
    actions: actions.map(actionFromDto),
    evidence: evidence.map(evidenceFromDto),
    escalatedToOperations: dto.status === 'transferred',
    createdAt: dto.created_at,
    closedAt: dto.closed_at,
    closedById: dto.closed_by_id,
    finalReport: dto.final_report,
  }
}
