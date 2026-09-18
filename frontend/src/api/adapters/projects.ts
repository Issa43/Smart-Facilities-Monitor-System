import type { Project, Stage, StageUpdate } from '@/types'

export interface ProjectDto {
  id: string
  name: string
  facility_id: string | null
  facility_type: Project['facilityType']
  description: string
  location: string
  latitude: string | null
  longitude: string | null
  image_available: boolean
  start_date: string
  expected_completion_date: string
  actual_completion_date: string | null
  status: Project['status']
  progress_percentage: string | number
  is_overdue: boolean
  primary_manager_id: string | null
  primary_manager_name: string | null
  current_phase_name: string | null
  created_by_id: string
  created_at: string
  updated_at: string
}

export interface ProjectAssignmentDto {
  id: string
  user: string
  user_name: string
  user_email: string
  role_type: 'primary_manager' | 'engineer' | 'supervisor' | 'viewer'
  created_by_id: string
  created_at: string
  is_active: boolean
}

export interface ProjectPhaseDto {
  id: string
  project_id: string
  name: string
  description: string
  sequence_number: number
  start_date: string
  expected_completion_date: string
  actual_start_date: string | null
  actual_completion_date: string | null
  initial_progress: string | number
  current_progress: string | number
  priority: Stage['priority']
  status: Stage['status']
  approved_by_id: string | null
  approved_at: string | null
  created_by_id: string
  created_at: string
  updated_at: string
}

export interface PhaseProgressDto {
  id: string
  phase_id: string
  progress_percentage: string | number
  work_completed: string
  notes: string
  created_by_id: string
  created_at: string
}

export interface PhaseReviewDto {
  id: string
  phase_id: string
  decision: 'approved' | 'rejected'
  disposition: 'needs_modification' | 'final_rejection' | null
  reason: string
  created_by_id: string
  created_at: string
}

const numberValue = (value: string | number): number =>
  typeof value === 'number' ? value : Number(value)

/** DRF serialises DecimalField as a string; absent coordinates stay null
 *  rather than collapsing to 0, which is a real point in the ocean. */
function numberOrNull(value: string | null): number | null {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function projectFromDto(dto: ProjectDto): Project {
  return {
    id: dto.id,
    name: dto.name,
    facilityType: dto.facility_type,
    description: dto.description,
    location: dto.location,
    latitude: numberOrNull(dto.latitude),
    longitude: numberOrNull(dto.longitude),
    startDate: dto.start_date,
    expectedEndDate: dto.expected_completion_date,
    status: dto.status,
    imageUrl: dto.image_available ? `/construction/projects/${dto.id}/image/` : null,
    constructionManagerId: dto.primary_manager_id ?? '',
    constructionManagerName: dto.primary_manager_name ?? undefined,
    progressPercent: numberValue(dto.progress_percentage),
    currentStageName: dto.current_phase_name ?? '—',
    updatedAt: dto.updated_at,
  }
}

export function phaseFromDto(dto: ProjectPhaseDto, reviewNote: string | null = null): Stage {
  return {
    id: dto.id,
    projectId: dto.project_id,
    name: dto.name,
    description: dto.description,
    startDate: dto.start_date,
    expectedEndDate: dto.expected_completion_date,
    progressPercent: numberValue(dto.current_progress),
    priority: dto.priority,
    status: dto.status,
    reviewNote,
    updatedAt: dto.updated_at,
  }
}

export function progressFromDto(dto: PhaseProgressDto): StageUpdate {
  return {
    id: dto.id,
    stageId: dto.phase_id,
    progressPercent: numberValue(dto.progress_percentage),
    completedWork: dto.work_completed,
    note: dto.notes,
    photoCount: 0,
    authorId: dto.created_by_id,
    createdAt: dto.created_at,
  }
}
