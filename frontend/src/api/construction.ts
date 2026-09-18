import type {
  DailyReport,
  Material,
  MaterialRequest,
  Priority,
  Project,
  ProjectDocument,
  QualityInspection,
  SitePhoto,
  Stage,
  StageUpdate,
} from '@/types'
import { apiRequest, downloadProtectedFile, fetchAllPages, saveDownloadedFile } from './client'
import {
  phaseFromDto,
  progressFromDto,
  projectFromDto,
  type PhaseProgressDto,
  type PhaseReviewDto,
  type ProjectDto,
  type ProjectPhaseDto,
} from './adapters/projects'

const queryPath = (path: string, params: Record<string, string | undefined>): string => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => value && query.set(key, value))
  return query.size ? `${path}?${query}` : path
}

export interface ProjectInput {
  name: string
  facilityType: Project['facilityType']
  description: string
  location: string
  latitude?: number | null
  longitude?: number | null
  startDate: string
  expectedEndDate: string
  status: Project['status']
  constructionManagerId: string
  image?: File | null
}

/**
 * Format one coordinate for `DecimalField(max_digits=9, decimal_places=6)`.
 *
 * A map click yields full float precision (34.80210123456789), which is 16
 * digits and the server rejects it outright. Six decimal places is the field's
 * limit and is ~11cm of ground resolution, far finer than a click can express.
 * Rounding can nudge a value past the edge of the range (179.9999999 ->
 * "180.000000" is fine, but -179.9999999 must not become -180.000001), so the
 * result is clamped to the bound the model validates against.
 */
function coordinate(value: number, bound: number): string {
  const clamped = Math.min(bound, Math.max(-bound, value))
  return clamped.toFixed(6)
}

function projectPayload(input: Partial<ProjectInput>): Record<string, unknown> | FormData {
  const payload: Record<string, string | File> = {}
  if (input.name !== undefined) payload.name = input.name
  if (input.facilityType !== undefined) payload.facility_type = input.facilityType
  if (input.description !== undefined) payload.description = input.description
  if (input.location !== undefined) payload.location = input.location
  // Only sent when a point was actually chosen: an untouched map must not
  // write coordinates, and must not clear existing ones on edit.
  if (input.latitude !== undefined && input.latitude !== null) {
    payload.latitude = coordinate(input.latitude, 90)
  }
  if (input.longitude !== undefined && input.longitude !== null) {
    payload.longitude = coordinate(input.longitude, 180)
  }
  if (input.startDate !== undefined) payload.start_date = input.startDate.slice(0, 10)
  if (input.expectedEndDate !== undefined) {
    payload.expected_completion_date = input.expectedEndDate.slice(0, 10)
  }
  if (input.constructionManagerId !== undefined) {
    payload.primary_manager_id = input.constructionManagerId
  }
  if (input.image) {
    const form = new FormData()
    Object.entries({ ...payload, image: input.image }).forEach(([key, value]) =>
      form.append(key, value),
    )
    return form
  }
  return payload
}

async function projectWithImage(dto: ProjectDto): Promise<Project> {
  const project = projectFromDto(dto)
  if (!dto.image_available) return project
  const image = await downloadProtectedFile(`/construction/projects/${dto.id}/image/`, dto.name)
  return { ...project, imageUrl: URL.createObjectURL(image.blob) }
}

export async function listProjects(_managerId?: string): Promise<Project[]> {
  const projects = await fetchAllPages<ProjectDto>('/construction/projects/')
  return Promise.all(projects.map(projectWithImage))
}

export async function getProject(id: string): Promise<Project> {
  return projectWithImage(await apiRequest<ProjectDto>(`/construction/projects/${id}/`))
}

export async function createProject(input: ProjectInput): Promise<Project> {
  const dto = await apiRequest<ProjectDto>('/projects/', {
    method: 'POST',
    body: projectPayload(input),
  })
  return projectWithImage(dto)
}

export async function updateProject(id: string, input: Partial<ProjectInput>): Promise<Project> {
  const dto = await apiRequest<ProjectDto>(`/projects/${id}/`, {
    method: 'PATCH',
    body: projectPayload(input),
  })
  return projectWithImage(dto)
}

export async function updateAssignedProject(
  id: string,
  input: Partial<Omit<ProjectInput, 'constructionManagerId'>>,
): Promise<Project> {
  const dto = await apiRequest<ProjectDto>(`/construction/projects/${id}/`, {
    method: 'PATCH',
    body: projectPayload(input),
  })
  return projectWithImage(dto)
}

export async function deleteProject(id: string): Promise<void> {
  await apiRequest(`/projects/${id}/`, { method: 'DELETE' })
}

export interface CompletionCheck {
  canComplete: boolean
  allStagesCompleted: boolean
  noRejectedStages: boolean
  noOpenMaterialRequests: boolean
  incompleteStageCount: number
  rejectedStageCount: number
  openRequestCount: number
}

interface CompletionCheckDto {
  can_complete: boolean
  all_stages_completed: boolean
  no_rejected_stages: boolean
  no_open_material_requests: boolean
  incomplete_stage_count: number
  rejected_stage_count: number
  open_request_count: number
}

export async function checkProjectCompletion(projectId: string): Promise<CompletionCheck> {
  const dto = await apiRequest<CompletionCheckDto>(
    `/construction/projects/${projectId}/completion-check/`,
  )
  return {
    canComplete: dto.can_complete,
    allStagesCompleted: dto.all_stages_completed,
    noRejectedStages: dto.no_rejected_stages,
    noOpenMaterialRequests: dto.no_open_material_requests,
    incompleteStageCount: dto.incomplete_stage_count,
    rejectedStageCount: dto.rejected_stage_count,
    openRequestCount: dto.open_request_count,
  }
}

export async function startProject(projectId: string): Promise<Project> {
  await apiRequest(`/projects/${projectId}/start/`, { method: 'POST' })
  return getProject(projectId)
}

export async function completeProject(
  projectId: string,
  actualCompletionDate = new Date().toISOString().slice(0, 10),
): Promise<Project> {
  await apiRequest(`/construction/projects/${projectId}/complete/`, {
    method: 'POST',
    body: { actual_completion_date: actualCompletionDate },
  })
  return getProject(projectId)
}

export async function convertProjectToFacility(projectId: string): Promise<void> {
  await apiRequest(`/projects/${projectId}/convert-to-facility/`, { method: 'POST' })
}

export interface StageInput {
  projectId: string
  name: string
  description: string
  startDate: string
  expectedEndDate: string
  priority: Priority
}

export async function listStages(projectId?: string): Promise<Stage[]> {
  const dtos = await fetchAllPages<ProjectPhaseDto>(
    queryPath('/construction/phases/', { project: projectId }),
  )
  return dtos.map((dto) => phaseFromDto(dto))
}

async function getStageWithoutReviews(id: string): Promise<Stage> {
  return phaseFromDto(await apiRequest<ProjectPhaseDto>(`/construction/phases/${id}/`))
}

export async function getStage(id: string): Promise<Stage> {
  const dto = await apiRequest<ProjectPhaseDto>(`/construction/phases/${id}/`)
  const reviews = await fetchAllPages<PhaseReviewDto>(
    `/projects/${dto.project_id}/phases/${id}/review-history/`,
  )
  const latestReview = reviews.toSorted((a, b) => b.created_at.localeCompare(a.created_at))[0]
  return phaseFromDto(dto, latestReview?.reason ?? null)
}

export async function createStage(input: StageInput): Promise<Stage> {
  const existing = await fetchAllPages<ProjectPhaseDto>(
    queryPath('/construction/phases/', { project: input.projectId }),
  )
  const sequence = existing.reduce((max, stage) => Math.max(max, stage.sequence_number), 0)
  const dto = await apiRequest<ProjectPhaseDto>(`/projects/${input.projectId}/phases/`, {
    method: 'POST',
    body: {
      name: input.name,
      description: input.description,
      sequence_number: sequence + 1,
      start_date: input.startDate.slice(0, 10),
      expected_completion_date: input.expectedEndDate.slice(0, 10),
      priority: input.priority,
    },
  })
  return phaseFromDto(dto)
}

export async function updateStage(
  id: string,
  input: Partial<StageInput> & { progressPercent?: number },
): Promise<Stage> {
  const current = await getStage(id)
  const dto = await apiRequest<ProjectPhaseDto>(`/projects/${current.projectId}/phases/${id}/`, {
    method: 'PATCH',
    body: {
      ...(input.name !== undefined ? { name: input.name } : {}),
      ...(input.description !== undefined ? { description: input.description } : {}),
      ...(input.startDate !== undefined ? { start_date: input.startDate.slice(0, 10) } : {}),
      ...(input.expectedEndDate !== undefined
        ? { expected_completion_date: input.expectedEndDate.slice(0, 10) }
        : {}),
      ...(input.priority !== undefined ? { priority: input.priority } : {}),
    },
  })
  if (input.progressPercent !== undefined && input.progressPercent !== current.progressPercent) {
    await apiRequest<PhaseProgressDto>(`/projects/${current.projectId}/phases/${id}/progress/`, {
      method: 'POST',
      body: {
        progress_percentage: input.progressPercent,
        work_completed: input.description || 'Progress updated',
        notes: '',
      },
    })
    return getStage(id)
  }
  return phaseFromDto(dto)
}

export async function deleteStage(id: string): Promise<void> {
  const stage = await getStage(id)
  await apiRequest(`/projects/${stage.projectId}/phases/${id}/`, { method: 'DELETE' })
}

export type StageReviewDecision = 'approve' | 'reject' | 'return'

export interface StageReview {
  id: string
  stageId: string
  decision: 'approved' | 'rejected'
  disposition: 'needs_modification' | 'final_rejection' | null
  reason: string
  reviewerId: string
  createdAt: string
}

export async function listStageReviews(stageId: string): Promise<StageReview[]> {
  const stage = await getStageWithoutReviews(stageId)
  const dtos = await fetchAllPages<PhaseReviewDto>(
    `/projects/${stage.projectId}/phases/${stageId}/review-history/`,
  )
  return dtos.map((dto) => ({
    id: dto.id,
    stageId: dto.phase_id,
    decision: dto.decision,
    disposition: dto.disposition,
    reason: dto.reason,
    reviewerId: dto.created_by_id,
    createdAt: dto.created_at,
  }))
}

export async function reviewStage(
  id: string,
  decision: StageReviewDecision,
  note: string,
): Promise<Stage> {
  const stage = await getStage(id)
  const action =
    decision === 'approve' ? 'approve' : decision === 'reject' ? 'reject' : 'request-modification'
  await apiRequest(`/projects/${stage.projectId}/phases/${id}/${action}/`, {
    method: 'POST',
    body: decision === 'approve' ? undefined : { reason: note },
  })
  return getStage(id)
}

export async function listStageUpdates(stageId: string): Promise<StageUpdate[]> {
  const stage = await getStage(stageId)
  const dtos = await fetchAllPages<PhaseProgressDto>(
    `/projects/${stage.projectId}/phases/${stageId}/progress-history/`,
  )
  return dtos.map(progressFromDto)
}

export async function addStageUpdate(input: {
  stageId: string
  progressPercent: number
  completedWork: string
  note: string
  photoCount: number
  authorId: string
}): Promise<StageUpdate> {
  const stage = await getStage(input.stageId)
  const dto = await apiRequest<PhaseProgressDto>(
    `/projects/${stage.projectId}/phases/${stage.id}/progress/`,
    {
      method: 'POST',
      body: {
        progress_percentage: input.progressPercent,
        work_completed: input.completedWork,
        notes: input.note,
      },
    },
  )
  return progressFromDto(dto)
}

interface MaterialDto {
  id: string
  project_id: string
  name: string
  unit: string
  quantity_required: string | number
  quantity_used: string | number
  quantity_remaining: string | number
  min_stock_threshold: string | number
}

const materialFromDto = (dto: MaterialDto): Material => ({
  id: dto.id,
  projectId: dto.project_id,
  name: dto.name,
  unit: dto.unit,
  requiredQty: Number(dto.quantity_required),
  usedQty: Number(dto.quantity_used),
  remainingQty: Number(dto.quantity_remaining),
  minStockThreshold: Number(dto.min_stock_threshold),
})

export interface MaterialInput {
  projectId: string
  name: string
  unit: string
  requiredQty: number
  minStockThreshold: number
}

export async function listMaterials(projectId?: string): Promise<Material[]> {
  const dtos = await fetchAllPages<MaterialDto>(
    queryPath('/construction/materials/', { project: projectId }),
  )
  return dtos.map(materialFromDto)
}

const materialBody = (input: Partial<MaterialInput>): Record<string, unknown> => ({
  ...(input.projectId !== undefined ? { project: input.projectId } : {}),
  ...(input.name !== undefined ? { name: input.name } : {}),
  ...(input.unit !== undefined ? { unit: input.unit } : {}),
  ...(input.requiredQty !== undefined ? { quantity_required: input.requiredQty } : {}),
  ...(input.minStockThreshold !== undefined
    ? { min_stock_threshold: input.minStockThreshold }
    : {}),
})

export async function createMaterial(input: MaterialInput): Promise<Material> {
  return materialFromDto(
    await apiRequest<MaterialDto>('/construction/materials/', {
      method: 'POST',
      body: materialBody(input),
    }),
  )
}

export async function updateMaterial(id: string, input: Partial<MaterialInput>): Promise<Material> {
  return materialFromDto(
    await apiRequest<MaterialDto>(`/construction/materials/${id}/`, {
      method: 'PATCH',
      body: materialBody(input),
    }),
  )
}

export async function deleteMaterial(id: string): Promise<void> {
  await apiRequest(`/construction/materials/${id}/`, { method: 'DELETE' })
}

interface MaterialConsumptionDto {
  id: string
  material: string
  quantity_used: string | number
  usage_date: string
  phase: string | null
  created_by_id: string
  created_at: string
}

export interface MaterialConsumption {
  id: string
  materialId: string
  quantity: number
  usageDate: string
  stageId: string | null
  authorId: string
  createdAt: string
}

const consumptionFromDto = (dto: MaterialConsumptionDto): MaterialConsumption => ({
  id: dto.id,
  materialId: dto.material,
  quantity: Number(dto.quantity_used),
  usageDate: dto.usage_date,
  stageId: dto.phase,
  authorId: dto.created_by_id,
  createdAt: dto.created_at,
})

export async function listMaterialConsumption(id: string): Promise<MaterialConsumption[]> {
  return (
    await fetchAllPages<MaterialConsumptionDto>(`/construction/materials/${id}/consumption/`)
  ).map(consumptionFromDto)
}

export async function consumeMaterial(
  id: string,
  quantity: number,
  usageDate = new Date().toISOString().slice(0, 10),
): Promise<MaterialConsumption> {
  return consumptionFromDto(
    await apiRequest<MaterialConsumptionDto>(`/construction/materials/${id}/consumption/`, {
      method: 'POST',
      body: { quantity, usage_date: usageDate },
    }),
  )
}

interface MaterialRequestDto {
  id: string
  project_id: string
  project_name: string
  material: string
  material_name: string
  unit: string
  quantity_requested: string | number
  reason: string
  priority: 'low' | 'medium' | 'high' | 'urgent'
  status: 'submitted' | 'reviewed' | 'approved' | 'rejected' | 'completed'
  requested_by_id: string
  requested_by_name: string
  created_at: string
}

const requestFromDto = (dto: MaterialRequestDto): MaterialRequest => ({
  id: dto.id,
  projectId: dto.project_id,
  projectName: dto.project_name,
  materialId: dto.material,
  materialName: dto.material_name,
  requestedQty: Number(dto.quantity_requested),
  unit: dto.unit,
  reason: dto.reason,
  priority: dto.priority === 'urgent' ? 'critical' : dto.priority,
  status:
    dto.status === 'completed'
      ? 'delivered'
      : dto.status === 'submitted' || dto.status === 'reviewed'
        ? 'pending'
        : dto.status,
  requestedById: dto.requested_by_id,
  requestedByName: dto.requested_by_name,
  createdAt: dto.created_at,
})

export interface MaterialRequestInput {
  projectId: string
  materialId: string
  requestedQty: number
  reason: string
  priority: Priority
}

export async function listMaterialRequests(projectId?: string): Promise<MaterialRequest[]> {
  const dtos = await fetchAllPages<MaterialRequestDto>(
    queryPath('/construction/material-requests/', { project: projectId }),
  )
  return dtos.map(requestFromDto)
}

export async function getMaterialRequest(id: string): Promise<MaterialRequest> {
  return requestFromDto(
    await apiRequest<MaterialRequestDto>(`/construction/material-requests/${id}/`),
  )
}

export async function createMaterialRequest(input: MaterialRequestInput): Promise<MaterialRequest> {
  const dto = await apiRequest<MaterialRequestDto>('/construction/material-requests/', {
    method: 'POST',
    body: {
      project: input.projectId,
      material: input.materialId,
      quantity_requested: input.requestedQty,
      reason: input.reason,
      priority: input.priority === 'critical' ? 'urgent' : input.priority,
    },
  })
  return requestFromDto(dto)
}

export async function setMaterialRequestStatus(
  id: string,
  status: MaterialRequest['status'],
): Promise<MaterialRequest> {
  if (status === 'approved') {
    await apiRequest(`/construction/material-requests/${id}/approve/`, { method: 'POST' })
  } else if (status === 'rejected') {
    await apiRequest(`/construction/material-requests/${id}/reject/`, { method: 'POST' })
  } else if (status === 'delivered') {
    await apiRequest(`/construction/material-requests/${id}/complete/`, { method: 'POST' })
  }
  return requestFromDto(
    await apiRequest<MaterialRequestDto>(`/construction/material-requests/${id}/`),
  )
}

interface InspectionDto {
  id: string
  project_id: string
  phase_id: string
  title: string
  inspector_id: string
  inspector_name: string
  score: string | number
  result: QualityInspection['result']
  notes: string
  inspected_at: string
}

const inspectionFromDto = (dto: InspectionDto): QualityInspection => ({
  id: dto.id,
  projectId: dto.project_id,
  stageId: dto.phase_id,
  title: dto.title,
  inspectorId: dto.inspector_id,
  inspectorName: dto.inspector_name,
  score: Number(dto.score),
  result: dto.result,
  notes: dto.notes,
  inspectedAt: dto.inspected_at,
})

export async function listInspections(projectId?: string): Promise<QualityInspection[]> {
  return (
    await fetchAllPages<InspectionDto>(
      queryPath('/construction/quality-inspections/', { project: projectId }),
    )
  ).map(inspectionFromDto)
}

export async function createInspection(input: {
  projectId: string
  stageId: string
  title: string
  inspectorId: string
  score: number
  result: QualityInspection['result']
  notes: string
}): Promise<QualityInspection> {
  return inspectionFromDto(
    await apiRequest<InspectionDto>('/construction/quality-inspections/', {
      method: 'POST',
      body: {
        project: input.projectId,
        phase: input.stageId,
        title: input.title,
        score: input.score,
        result: input.result,
        notes: input.notes,
      },
    }),
  )
}

export async function deleteInspection(id: string): Promise<void> {
  await apiRequest(`/construction/quality-inspections/${id}/`, { method: 'DELETE' })
}

interface DailyReportDto {
  id: string
  project_id: string
  title: string
  summary: string
  progress_percentage: string | number
  workforce_count: number
  photo_count: number
  author_id: string
  author_name: string
  report_date: string
}

const dailyReportFromDto = (dto: DailyReportDto): DailyReport => ({
  id: dto.id,
  projectId: dto.project_id,
  title: dto.title,
  summary: dto.summary,
  progressPercent: Number(dto.progress_percentage),
  workforceCount: dto.workforce_count,
  photoCount: dto.photo_count,
  authorId: dto.author_id,
  authorName: dto.author_name,
  reportDate: dto.report_date,
})

export async function listDailyReports(projectId?: string): Promise<DailyReport[]> {
  return (
    await fetchAllPages<DailyReportDto>(
      queryPath('/construction/daily-reports/', { project: projectId }),
    )
  ).map(dailyReportFromDto)
}

export interface DailyReportInput {
  projectId: string
  title: string
  summary: string
  progressPercent: number
  workforceCount: number
  reportDate: string
}

export type DailyReportUpdateInput = Partial<Omit<DailyReportInput, 'projectId'>>

const dailyReportBody = (input: Partial<DailyReportInput>): Record<string, string | number> => ({
  ...(input.projectId !== undefined ? { project: input.projectId } : {}),
  ...(input.title !== undefined ? { title: input.title } : {}),
  ...(input.summary !== undefined ? { summary: input.summary } : {}),
  ...(input.progressPercent !== undefined ? { progress_percentage: input.progressPercent } : {}),
  ...(input.workforceCount !== undefined ? { workforce_count: input.workforceCount } : {}),
  ...(input.reportDate !== undefined ? { report_date: input.reportDate.slice(0, 10) } : {}),
})

export async function getDailyReport(id: string): Promise<DailyReport> {
  return dailyReportFromDto(await apiRequest<DailyReportDto>(`/construction/daily-reports/${id}/`))
}

export async function createDailyReport(input: DailyReportInput): Promise<DailyReport> {
  return dailyReportFromDto(
    await apiRequest<DailyReportDto>('/construction/daily-reports/', {
      method: 'POST',
      body: dailyReportBody(input),
    }),
  )
}

export async function updateDailyReport(
  id: string,
  input: DailyReportUpdateInput,
): Promise<DailyReport> {
  return dailyReportFromDto(
    await apiRequest<DailyReportDto>(`/construction/daily-reports/${id}/`, {
      method: 'PATCH',
      body: dailyReportBody(input),
    }),
  )
}

export async function deleteDailyReport(id: string): Promise<void> {
  await apiRequest(`/construction/daily-reports/${id}/`, { method: 'DELETE' })
}

interface DocumentDto {
  id: string
  project_id: string
  title: string
  document_type: ProjectDocument['category']
  original_file_name: string
  mime_type: string
  file_size: number
  uploaded_by_id: string
  uploaded_by_name: string
  uploaded_at: string
  download_url: string | null
}

const extensionType = (name: string): ProjectDocument['fileType'] => {
  const extension = name.split('.').pop()?.toLowerCase()
  return extension === 'dwg' || extension === 'xlsx' || extension === 'docx' || extension === 'jpg'
    ? extension
    : 'pdf'
}

const documentFromDto = (dto: DocumentDto): ProjectDocument => ({
  id: dto.id,
  projectId: dto.project_id,
  name: dto.title,
  category: dto.document_type,
  fileType: extensionType(dto.original_file_name),
  sizeKb: Math.ceil(dto.file_size / 1024),
  uploadedById: dto.uploaded_by_id,
  uploadedByName: dto.uploaded_by_name,
  uploadedAt: dto.uploaded_at,
  originalFileName: dto.original_file_name,
  downloadUrl: dto.download_url,
})

export async function listDocuments(projectId?: string): Promise<ProjectDocument[]> {
  return (
    await fetchAllPages<DocumentDto>(queryPath('/construction/documents/', { project: projectId }))
  ).map(documentFromDto)
}

export async function createDocument(input: {
  projectId: string | null
  name: string
  category: ProjectDocument['category']
  file: File
}): Promise<ProjectDocument> {
  if (!input.projectId) throw new Error('A project is required for project documents.')
  const form = new FormData()
  form.append('project', input.projectId)
  form.append('title', input.name)
  form.append('document_type', input.category)
  form.append('file', input.file)
  return documentFromDto(
    await apiRequest<DocumentDto>('/construction/documents/', { method: 'POST', body: form }),
  )
}

export async function deleteDocument(id: string): Promise<void> {
  await apiRequest(`/construction/documents/${id}/`, { method: 'DELETE' })
}

export async function downloadDocument(id: string, filename: string): Promise<void> {
  saveDownloadedFile(
    await downloadProtectedFile(`/construction/documents/${id}/download/`, filename),
  )
}

interface SitePhotoDto {
  id: string
  project_id: string
  phase_id: string | null
  caption: string
  captured_at: string
  original_file_name: string
}

async function sitePhotoFromDto(dto: SitePhotoDto): Promise<SitePhoto> {
  const image = await downloadProtectedFile(
    `/construction/site-photos/${dto.id}/download/`,
    dto.original_file_name,
  )
  return {
    id: dto.id,
    projectId: dto.project_id,
    stageId: dto.phase_id,
    caption: dto.caption,
    gradient: `url("${URL.createObjectURL(image.blob)}") center / cover no-repeat`,
    takenAt: dto.captured_at,
  }
}

export async function listSitePhotos(projectId?: string): Promise<SitePhoto[]> {
  const dtos = await fetchAllPages<SitePhotoDto>(
    queryPath('/construction/site-photos/', { project: projectId }),
  )
  return Promise.all(dtos.map(sitePhotoFromDto))
}

export async function createSitePhoto(input: {
  projectId: string
  stageId: string | null
  caption: string
  file: File
}): Promise<SitePhoto> {
  const form = new FormData()
  form.append('project', input.projectId)
  if (input.stageId) form.append('phase', input.stageId)
  form.append('caption', input.caption)
  form.append('captured_at', new Date().toISOString())
  form.append('image', input.file)
  return sitePhotoFromDto(
    await apiRequest<SitePhotoDto>('/construction/site-photos/', { method: 'POST', body: form }),
  )
}

export async function deleteSitePhoto(id: string): Promise<void> {
  await apiRequest(`/construction/site-photos/${id}/`, { method: 'DELETE' })
}
