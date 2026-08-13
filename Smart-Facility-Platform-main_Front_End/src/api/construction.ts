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
import type { Database } from './fixtures'
import { badRequest, delay, newId, notFound, nowIso } from './client'
import { clone, commit, getDb } from './db'

/* ==========================================================================
   Projects
   ========================================================================== */

export interface ProjectInput {
  name: string
  facilityType: Project['facilityType']
  description: string
  location: string
  startDate: string
  expectedEndDate: string
  status: Project['status']
  constructionManagerId: string
}

export async function listProjects(managerId?: string): Promise<Project[]> {
  await delay()
  const all = getDb().projects
  return clone(managerId ? all.filter((p) => p.constructionManagerId === managerId) : all)
}

export async function getProject(id: string): Promise<Project> {
  await delay()
  const project = getDb().projects.find((p) => p.id === id)
  return project ? clone(project) : notFound('المشروع')
}

export async function createProject(input: ProjectInput): Promise<Project> {
  await delay()
  return commit((db) => {
    const project: Project = {
      id: newId('prj'),
      ...input,
      imageUrl: null,
      progressPercent: 0,
      currentStageName: 'لم تبدأ المراحل',
      updatedAt: nowIso(),
    }
    db.projects.unshift(project)
    return clone(project)
  })
}

export async function updateProject(id: string, input: Partial<ProjectInput>): Promise<Project> {
  await delay()
  return commit((db) => {
    const project = db.projects.find((p) => p.id === id)
    if (!project) notFound('المشروع')
    Object.assign(project, input, { updatedAt: nowIso() })
    return clone(project)
  })
}

export async function deleteProject(id: string): Promise<void> {
  await delay()
  commit((db) => {
    if (!db.projects.some((p) => p.id === id)) notFound('المشروع')
    db.projects = db.projects.filter((p) => p.id !== id)
    db.stages = db.stages.filter((s) => s.projectId !== id)
    db.materials = db.materials.filter((m) => m.projectId !== id)
    db.materialRequests = db.materialRequests.filter((r) => r.projectId !== id)
  })
}

/**
 * Requirement: a project may only move to the operations phase when
 *   - every stage is completed,
 *   - no stage is rejected,
 *   - no material request is still open.
 *
 * Returned as a structured result rather than a thrown error so the UI can show
 * the checklist *before* the user presses the button, not only after it fails.
 */
export interface CompletionCheck {
  canComplete: boolean
  allStagesCompleted: boolean
  noRejectedStages: boolean
  noOpenMaterialRequests: boolean
  incompleteStageCount: number
  rejectedStageCount: number
  openRequestCount: number
}

function evaluateCompletion(db: Database, projectId: string): CompletionCheck {
  const stages = db.stages.filter((s) => s.projectId === projectId)
  const requests = db.materialRequests.filter((r) => r.projectId === projectId)

  const incomplete = stages.filter((s) => s.status !== 'completed')
  const rejected = stages.filter((s) => s.status === 'rejected')
  const open = requests.filter((r) => r.status === 'pending' || r.status === 'approved')

  // Rejected stages are also incomplete, so exclude them from the first count
  // to keep the two checklist lines from double-reporting the same stage.
  const incompleteCount = incomplete.filter((s) => s.status !== 'rejected').length

  return {
    allStagesCompleted: stages.length > 0 && incomplete.length === 0,
    noRejectedStages: rejected.length === 0,
    noOpenMaterialRequests: open.length === 0,
    incompleteStageCount: incompleteCount,
    rejectedStageCount: rejected.length,
    openRequestCount: open.length,
    canComplete: stages.length > 0 && incomplete.length === 0 && open.length === 0,
  }
}

export async function checkProjectCompletion(projectId: string): Promise<CompletionCheck> {
  await delay(160)
  return evaluateCompletion(getDb(), projectId)
}

/** Hands the project over: it becomes an operational facility. */
export async function completeProject(projectId: string): Promise<Project> {
  await delay(500)
  return commit((db) => {
    const project = db.projects.find((p) => p.id === projectId)
    if (!project) notFound('المشروع')

    const check = evaluateCompletion(db, projectId)
    if (!check.canComplete) {
      badRequest('لا يمكن إنهاء المشروع — يجب اكتمال جميع المراحل وإغلاق طلبات المواد المفتوحة')
    }

    project.status = 'operational'
    project.progressPercent = 100
    project.currentStageName = 'مكتمل ومسلّم'
    project.updatedAt = nowIso()

    db.facilities.push({
      id: newId('fac'),
      projectId: project.id,
      name: project.name,
      type: project.facilityType,
      location: project.location,
      operationStartDate: nowIso(),
      status: 'operational',
      assetCount: 0,
      uptimePercent: 100,
      operationsManagerId: 'usr-operations',
    })

    db.notifications.unshift({
      id: newId('ntf'),
      title: 'مشروع تحوّل إلى منشأة تشغيلية',
      body: `تم تسليم "${project.name}" وتحويله إلى مرحلة التشغيل.`,
      category: 'project',
      tone: 'success',
      read: false,
      audience: ['super_admin', 'operations_manager'],
      href: null,
      createdAt: nowIso(),
    })

    return clone(project)
  })
}

/* ==========================================================================
   Stages
   ========================================================================== */

export interface StageInput {
  projectId: string
  name: string
  description: string
  startDate: string
  expectedEndDate: string
  progressPercent: number
  priority: Priority
  status: Stage['status']
}

export async function listStages(projectId?: string): Promise<Stage[]> {
  await delay()
  const all = getDb().stages
  return clone(projectId ? all.filter((s) => s.projectId === projectId) : all)
}

export async function getStage(id: string): Promise<Stage> {
  await delay()
  const stage = getDb().stages.find((s) => s.id === id)
  return stage ? clone(stage) : notFound('المرحلة')
}

export async function createStage(input: StageInput): Promise<Stage> {
  await delay()
  return commit((db) => {
    const stage: Stage = { id: newId('stg'), ...input, reviewNote: null, updatedAt: nowIso() }
    db.stages.push(stage)
    recalcProjectProgress(db, input.projectId)
    return clone(stage)
  })
}

export async function updateStage(id: string, input: Partial<StageInput>): Promise<Stage> {
  await delay()
  return commit((db) => {
    const stage = db.stages.find((s) => s.id === id)
    if (!stage) notFound('المرحلة')
    Object.assign(stage, input, { updatedAt: nowIso() })
    recalcProjectProgress(db, stage.projectId)
    return clone(stage)
  })
}

/** Requirement: a stage may only be deleted before execution starts. */
export async function deleteStage(id: string): Promise<void> {
  await delay()
  commit((db) => {
    const stage = db.stages.find((s) => s.id === id)
    if (!stage) notFound('المرحلة')
    if (stage.status !== 'not_started' || stage.progressPercent > 0) {
      badRequest('لا يمكن حذف مرحلة بدأ تنفيذها')
    }
    const { projectId } = stage
    db.stages = db.stages.filter((s) => s.id !== id)
    recalcProjectProgress(db, projectId)
  })
}

export type StageReviewDecision = 'approve' | 'reject' | 'return'

/** The quality gate: approve, reject, or send back for rework. */
export async function reviewStage(
  id: string,
  decision: StageReviewDecision,
  note: string,
): Promise<Stage> {
  await delay(400)
  return commit((db) => {
    const stage = db.stages.find((s) => s.id === id)
    if (!stage) notFound('المرحلة')

    if (decision === 'approve') {
      stage.status = 'completed'
      stage.progressPercent = 100
    } else if (decision === 'reject') {
      stage.status = 'rejected'
    } else {
      stage.status = 'in_progress'
    }

    stage.reviewNote = note
    stage.updatedAt = nowIso()
    recalcProjectProgress(db, stage.projectId)
    return clone(stage)
  })
}

export async function listStageUpdates(stageId: string): Promise<StageUpdate[]> {
  await delay()
  return clone(
    getDb()
      .stageUpdates.filter((u) => u.stageId === stageId)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
  )
}

export async function addStageUpdate(input: {
  stageId: string
  progressPercent: number
  completedWork: string
  note: string
  photoCount: number
  authorId: string
}): Promise<StageUpdate> {
  await delay()
  return commit((db) => {
    const stage = db.stages.find((s) => s.id === input.stageId)
    if (!stage) notFound('المرحلة')

    const update: StageUpdate = { id: newId('upd'), ...input, createdAt: nowIso() }
    db.stageUpdates.unshift(update)

    stage.progressPercent = input.progressPercent
    stage.status = input.progressPercent >= 100 ? 'under_review' : 'in_progress'
    stage.updatedAt = nowIso()
    recalcProjectProgress(db, stage.projectId)

    return clone(update)
  })
}

/** A project's progress is the mean of its stages — never edited directly. */
function recalcProjectProgress(db: Database, projectId: string): void {
  const project = db.projects.find((p) => p.id === projectId)
  if (!project) return

  const stages = db.stages.filter((s) => s.projectId === projectId)
  if (stages.length === 0) {
    project.progressPercent = 0
    project.currentStageName = 'لم تبدأ المراحل'
  } else {
    const total = stages.reduce((sum, s) => sum + s.progressPercent, 0)
    project.progressPercent = Math.round(total / stages.length)

    const active =
      stages.find((s) => s.status === 'in_progress') ??
      stages.find((s) => s.status === 'under_review') ??
      stages.find((s) => s.status === 'not_started')
    project.currentStageName = active?.name ?? 'جميع المراحل مكتملة'
  }
  project.updatedAt = nowIso()
}

/* ==========================================================================
   Materials
   ========================================================================== */

export interface MaterialInput {
  projectId: string
  name: string
  unit: string
  requiredQty: number
  usedQty: number
  minStockThreshold: number
}

export async function listMaterials(projectId?: string): Promise<Material[]> {
  await delay()
  const all = getDb().materials
  return clone(projectId ? all.filter((m) => m.projectId === projectId) : all)
}

export async function createMaterial(input: MaterialInput): Promise<Material> {
  await delay()
  return commit((db) => {
    const material: Material = {
      id: newId('mat'),
      ...input,
      remainingQty: input.requiredQty - input.usedQty,
    }
    db.materials.push(material)
    raiseLowStockNotification(db, material)
    return clone(material)
  })
}

export async function updateMaterial(id: string, input: Partial<MaterialInput>): Promise<Material> {
  await delay()
  return commit((db) => {
    const material = db.materials.find((m) => m.id === id)
    if (!material) notFound('المادة')

    Object.assign(material, input)
    material.remainingQty = material.requiredQty - material.usedQty
    raiseLowStockNotification(db, material)
    return clone(material)
  })
}

export async function deleteMaterial(id: string): Promise<void> {
  await delay()
  commit((db) => {
    if (!db.materials.some((m) => m.id === id)) notFound('المادة')
    db.materials = db.materials.filter((m) => m.id !== id)
  })
}

/**
 * Requirement: dropping below the minimum stock threshold raises an automatic
 * notification. Guarded against duplicates so editing a low row repeatedly does
 * not spam the drawer.
 */
function raiseLowStockNotification(db: Database, material: Material): void {
  if (material.remainingQty >= material.minStockThreshold) return

  const alreadyRaised = db.notifications.some(
    (n) => n.category === 'material' && n.body.includes(material.name) && !n.read,
  )
  if (alreadyRaised) return

  db.notifications.unshift({
    id: newId('ntf'),
    title: 'انخفاض مخزون عن الحد الأدنى',
    body: `الكمية المتبقية من "${material.name}" (${material.remainingQty} ${material.unit}) أقل من الحد الأدنى (${material.minStockThreshold}).`,
    category: 'material',
    tone: 'warning',
    read: false,
    audience: ['construction_manager', 'super_admin'],
    href: null,
    createdAt: nowIso(),
  })
}

/* ==========================================================================
   Material requests
   ========================================================================== */

export interface MaterialRequestInput {
  projectId: string
  materialName: string
  requestedQty: number
  unit: string
  reason: string
  priority: Priority
  requestedById: string
}

export async function listMaterialRequests(projectId?: string): Promise<MaterialRequest[]> {
  await delay()
  const all = getDb().materialRequests
  return clone(projectId ? all.filter((r) => r.projectId === projectId) : all)
}

export async function createMaterialRequest(input: MaterialRequestInput): Promise<MaterialRequest> {
  await delay()
  return commit((db) => {
    const request: MaterialRequest = {
      id: newId('mrq'),
      ...input,
      status: 'pending',
      createdAt: nowIso(),
    }
    db.materialRequests.unshift(request)
    return clone(request)
  })
}

export async function setMaterialRequestStatus(
  id: string,
  status: MaterialRequest['status'],
): Promise<MaterialRequest> {
  await delay(300)
  return commit((db) => {
    const request = db.materialRequests.find((r) => r.id === id)
    if (!request) notFound('طلب المواد')
    request.status = status
    return clone(request)
  })
}

/* ==========================================================================
   Quality, reports, documents, photos
   ========================================================================== */

export async function listInspections(projectId?: string): Promise<QualityInspection[]> {
  await delay()
  const all = getDb().qualityInspections
  return clone(projectId ? all.filter((i) => i.projectId === projectId) : all)
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
  await delay()
  return commit((db) => {
    const inspection: QualityInspection = { id: newId('qin'), ...input, inspectedAt: nowIso() }
    db.qualityInspections.unshift(inspection)
    return clone(inspection)
  })
}

export async function listDailyReports(projectId?: string): Promise<DailyReport[]> {
  await delay()
  const all = getDb().dailyReports
  return clone(projectId ? all.filter((r) => r.projectId === projectId) : all)
}

export async function createDailyReport(input: {
  projectId: string
  title: string
  summary: string
  progressPercent: number
  workforceCount: number
  photoCount: number
  authorId: string
}): Promise<DailyReport> {
  await delay()
  return commit((db) => {
    const report: DailyReport = { id: newId('drp'), ...input, reportDate: nowIso() }
    db.dailyReports.unshift(report)
    return clone(report)
  })
}

export async function listDocuments(projectId?: string): Promise<ProjectDocument[]> {
  await delay()
  const all = getDb().documents
  return clone(projectId ? all.filter((d) => d.projectId === projectId) : all)
}

export async function createDocument(input: {
  projectId: string | null
  name: string
  category: ProjectDocument['category']
  fileType: ProjectDocument['fileType']
  sizeKb: number
  uploadedById: string
}): Promise<ProjectDocument> {
  await delay()
  return commit((db) => {
    const document: ProjectDocument = { id: newId('doc'), ...input, uploadedAt: nowIso() }
    db.documents.unshift(document)
    return clone(document)
  })
}

export async function deleteDocument(id: string): Promise<void> {
  await delay()
  commit((db) => {
    db.documents = db.documents.filter((d) => d.id !== id)
  })
}

export async function listSitePhotos(projectId?: string): Promise<SitePhoto[]> {
  await delay()
  const all = getDb().sitePhotos
  return clone(projectId ? all.filter((p) => p.projectId === projectId) : all)
}

export async function createSitePhoto(input: {
  projectId: string
  stageId: string | null
  caption: string
  gradient: string
}): Promise<SitePhoto> {
  await delay()
  return commit((db) => {
    const photo: SitePhoto = { id: newId('pho'), ...input, takenAt: nowIso() }
    db.sitePhotos.unshift(photo)
    return clone(photo)
  })
}
