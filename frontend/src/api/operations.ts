import type { Asset, Facility, Fault, Priority, WorkOrder } from '@/types'
import { apiRequest, fetchAllPages, unsupported, type PaginatedResponse } from './client'
import {
  assetFromDto,
  facilityFromDto,
  faultFromDto,
  faultSeverityToDto,
  priorityToDto,
  workOrderFromDto,
  type AssetDto,
  type FacilityDto,
  type FacilityMonitoringDto,
  type FaultDto,
  type MaintenanceOrderDto,
} from './adapters/operations'

function queryPath(path: string, params: Record<string, string | undefined>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value) query.set(key, value)
  const suffix = query.toString()
  return suffix ? `${path}?${suffix}` : path
}

/* ========================================================================== */
/* Facilities                                                                  */
/* ========================================================================== */

export async function listFacilities(): Promise<Facility[]> {
  const facilities = await fetchAllPages<FacilityDto>('/facilities/')
  return facilities.map((dto) => facilityFromDto(dto))
}

export async function getFacility(id: string): Promise<Facility> {
  return facilityFromDto(await apiRequest<FacilityDto>(`/facilities/${id}/`))
}

export async function getFacilityMonitoring(id: string): Promise<FacilityMonitoringDto> {
  return apiRequest<FacilityMonitoringDto>(`/facilities/${id}/monitoring/`)
}

/* ========================================================================== */
/* Assets                                                                      */
/* ========================================================================== */

export interface AssetInput {
  facilityId: string
  name: string
  assetType: string
  category: Asset['category']
  manufacturer: string
  model: string
  locationInFacility: string
  serialNumber: string
  installDate: string
  commissionDate: string
  notes: string
}

export interface AssetListOptions {
  page?: number
  search?: string
  facilityId?: string
  status?: Asset['status']
  assetType?: string
  category?: string
  manufacturer?: string
  location?: string
  ordering?: string
}

export interface AssetPage {
  count: number
  totalPages: number
  currentPage: number
  pageSize: number
  results: Asset[]
}

export interface AssetFilterOptions {
  assetTypes: string[]
  categories: string[]
  manufacturers: string[]
}

export interface AssetMonitoring {
  total: number
  averageHealthScore: number | null
  statusCounts: Record<Asset['status'], number>
}

function assetPayload(input: Partial<AssetInput>): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  if (input.facilityId !== undefined) payload.facility = input.facilityId
  if (input.name !== undefined) payload.name = input.name
  if (input.assetType !== undefined) payload.asset_type = input.assetType
  if (input.category !== undefined) payload.category = input.category
  if (input.manufacturer !== undefined) payload.manufacturer = input.manufacturer
  if (input.model !== undefined) payload.model = input.model
  if (input.locationInFacility !== undefined) {
    payload.location_inside_facility = input.locationInFacility
  }
  if (input.serialNumber !== undefined) payload.serial_number = input.serialNumber
  if (input.installDate !== undefined) payload.installation_date = input.installDate.slice(0, 10)
  if (input.commissionDate !== undefined) {
    payload.operation_date = input.commissionDate ? input.commissionDate.slice(0, 10) : null
  }
  if (input.notes !== undefined) payload.notes = input.notes
  return payload
}

async function faultCounts(facilityId?: string): Promise<Map<string, number>> {
  const faults = await fetchAllPages<FaultDto>(
    queryPath('/faults/', { asset__facility: facilityId }),
  )
  const counts = new Map<string, number>()
  for (const fault of faults) counts.set(fault.asset_id, (counts.get(fault.asset_id) ?? 0) + 1)
  return counts
}

export async function listAssets(facilityId?: string): Promise<Asset[]> {
  const [assets, counts] = await Promise.all([
    fetchAllPages<AssetDto>(queryPath('/assets/', { facility: facilityId })),
    faultCounts(facilityId),
  ])
  return assets.map((asset) => assetFromDto(asset, counts.get(asset.id) ?? 0))
}

export async function listAssetsPage(options: AssetListOptions = {}): Promise<AssetPage> {
  const page = await apiRequest<PaginatedResponse<AssetDto>>(
    queryPath('/assets/', {
      page: options.page ? String(options.page) : undefined,
      search: options.search,
      facility: options.facilityId,
      current_status: options.status,
      asset_type: options.assetType,
      category: options.category,
      manufacturer: options.manufacturer,
      location_inside_facility: options.location,
      ordering: options.ordering,
    }),
  )
  return {
    count: page.count,
    totalPages: page.total_pages,
    currentPage: page.current_page,
    pageSize: page.page_size,
    results: page.results.map((dto) => assetFromDto(dto)),
  }
}

export async function getAssetFilterOptions(): Promise<AssetFilterOptions> {
  const response = await apiRequest<{
    asset_types: string[]
    categories: string[]
    manufacturers: string[]
  }>('/assets/filter-options/')
  return {
    assetTypes: response.asset_types,
    categories: response.categories,
    manufacturers: response.manufacturers,
  }
}

export async function getAssetMonitoring(
  options: Omit<AssetListOptions, 'page' | 'ordering'> = {},
): Promise<AssetMonitoring> {
  const response = await apiRequest<{
    total: number
    average_health_score: string | number | null
    status_counts: Record<Asset['status'], number>
  }>(
    queryPath('/assets/monitoring/', {
      search: options.search,
      facility: options.facilityId,
      current_status: options.status,
      asset_type: options.assetType,
      category: options.category,
      manufacturer: options.manufacturer,
      location_inside_facility: options.location,
    }),
  )
  return {
    total: response.total,
    averageHealthScore:
      response.average_health_score == null ? null : Number(response.average_health_score),
    statusCounts: response.status_counts,
  }
}

export async function getAsset(id: string): Promise<Asset> {
  const [asset, faults] = await Promise.all([
    apiRequest<AssetDto>(`/assets/${id}/`),
    fetchAllPages<FaultDto>(queryPath('/faults/', { asset: id })),
  ])
  return assetFromDto(asset, faults.length)
}

export async function createAsset(input: AssetInput): Promise<Asset> {
  const dto = await apiRequest<AssetDto>('/assets/', {
    method: 'POST',
    body: assetPayload(input),
  })
  return assetFromDto(dto)
}

export async function updateAsset(id: string, input: Partial<AssetInput>): Promise<Asset> {
  const metadata = assetPayload(input)
  const dto =
    Object.keys(metadata).length > 0
      ? await apiRequest<AssetDto>(`/assets/${id}/`, { method: 'PATCH', body: metadata })
      : await apiRequest<AssetDto>(`/assets/${id}/`)
  return assetFromDto(dto)
}

export async function transitionAssetStatus(id: string, status: Asset['status']): Promise<Asset> {
  const dto = await apiRequest<AssetDto>(`/assets/${id}/transition-status/`, {
    method: 'POST',
    body: { target_status: status },
  })
  return assetFromDto(dto)
}

export async function deleteAsset(id: string): Promise<void> {
  await apiRequest(`/assets/${id}/`, { method: 'DELETE' })
}

/* ========================================================================== */
/* Maintenance orders                                                          */
/* ========================================================================== */

export interface WorkOrderInput {
  assetId: string
  assetType: string
  facilityId: string
  maintenanceType: WorkOrder['maintenanceType']
  reason: string
  description: string
  priority: Priority
  scheduledDate: string
  assignedToId: string | null
  tasks: string[]
}

function workOrderPayload(input: Partial<WorkOrderInput>): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  if (input.assetId !== undefined) payload.asset = input.assetId
  if (input.assetType !== undefined) payload.asset_type = input.assetType
  if (input.maintenanceType !== undefined) payload.type = input.maintenanceType
  if (input.reason !== undefined) payload.reason = input.reason
  if (input.description !== undefined) payload.description = input.description
  if (input.priority !== undefined) payload.priority = priorityToDto[input.priority]
  if (input.scheduledDate !== undefined) {
    payload.expected_execution_date = input.scheduledDate.slice(0, 10)
  }
  if (input.assignedToId !== undefined) payload.assigned_to = input.assignedToId
  if (input.tasks !== undefined) payload.tasks = input.tasks
  return payload
}

export async function listWorkOrders(facilityId?: string, assetId?: string): Promise<WorkOrder[]> {
  const dtos = await fetchAllPages<MaintenanceOrderDto>(
    queryPath('/maintenance/orders/', { asset__facility: facilityId, asset: assetId }),
  )
  return dtos.map(workOrderFromDto)
}

export async function getWorkOrder(id: string): Promise<WorkOrder> {
  return workOrderFromDto(await apiRequest<MaintenanceOrderDto>(`/maintenance/orders/${id}/`))
}

export async function createWorkOrder(input: WorkOrderInput): Promise<WorkOrder> {
  return workOrderFromDto(
    await apiRequest<MaintenanceOrderDto>('/maintenance/orders/', {
      method: 'POST',
      body: workOrderPayload(input),
    }),
  )
}

export async function updateWorkOrder(
  id: string,
  input: Partial<WorkOrderInput> & { notes?: string },
): Promise<WorkOrder> {
  let updated: MaintenanceOrderDto | undefined
  if (input.notes !== undefined) {
    updated = await apiRequest<MaintenanceOrderDto>(`/maintenance/orders/${id}/notes/`, {
      method: 'PATCH',
      body: { notes: input.notes },
    })
  }
  const payload = workOrderPayload(input)
  if (Object.keys(payload).length > 0) {
    updated = await apiRequest<MaintenanceOrderDto>(`/maintenance/orders/${id}/`, {
      method: 'PATCH',
      body: payload,
    })
  }
  if (!updated) updated = await apiRequest<MaintenanceOrderDto>(`/maintenance/orders/${id}/`)
  return workOrderFromDto(updated)
}

export async function setWorkOrderStatus(
  id: string,
  status: WorkOrder['status'],
  cancellationReason?: string,
): Promise<WorkOrder> {
  if (status === 'cancelled') {
    if (!cancellationReason?.trim()) {
      throw new Error('سبب إلغاء أمر الصيانة مطلوب.')
    }
    return workOrderFromDto(
      await apiRequest<MaintenanceOrderDto>(`/maintenance/orders/${id}/cancel/`, {
        method: 'POST',
        body: { reason: cancellationReason.trim() },
      }),
    )
  }
  if (status === 'assigned' || status === 'open') {
    const current = await apiRequest<MaintenanceOrderDto>(`/maintenance/orders/${id}/`)
    return workOrderFromDto(
      await apiRequest<MaintenanceOrderDto>(`/maintenance/orders/${id}/`, {
        method: 'PATCH',
        body: { assigned_to: status === 'open' ? null : current.assigned_to_id },
      }),
    )
  }
  const action = status === 'in_progress' ? 'start' : status === 'completed' ? 'complete' : 'close'
  const body =
    status === 'completed'
      ? { actual_completion_date: new Date().toISOString().slice(0, 10) }
      : undefined
  return workOrderFromDto(
    await apiRequest<MaintenanceOrderDto>(`/maintenance/orders/${id}/${action}/`, {
      method: 'POST',
      body,
    }),
  )
}

export async function toggleWorkOrderTask(orderId: string, taskId: string): Promise<WorkOrder> {
  const order = await getWorkOrder(orderId)
  const task = order.tasks.find((candidate) => candidate.id === taskId)
  if (!task) throw new Error('The maintenance task no longer exists.')
  await apiRequest(`/maintenance/orders/${orderId}/tasks/${taskId}/`, {
    method: 'PATCH',
    body: { completed: !task.done },
  })
  return getWorkOrder(orderId)
}

/* ========================================================================== */
/* Faults                                                                      */
/* ========================================================================== */

export interface FaultInput {
  assetId: string
  facilityId: string
  faultType: string
  description: string
  severity: Fault['severity']
  assignedToId: string | null
}

function faultPayload(input: Partial<FaultInput>): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  if (input.assetId !== undefined) payload.asset = input.assetId
  if (input.faultType !== undefined) payload.fault_type = input.faultType
  if (input.description !== undefined) payload.description = input.description
  if (input.severity !== undefined) payload.severity = faultSeverityToDto[input.severity]
  return payload
}

export async function listFaults(facilityId?: string, assetId?: string): Promise<Fault[]> {
  const dtos = await fetchAllPages<FaultDto>(
    queryPath('/faults/', { asset__facility: facilityId, asset: assetId }),
  )
  return dtos.map(faultFromDto)
}

export async function getFault(id: string): Promise<Fault> {
  return faultFromDto(await apiRequest<FaultDto>(`/faults/${id}/`))
}

export async function createFault(input: FaultInput): Promise<Fault> {
  let dto = await apiRequest<FaultDto>('/faults/', {
    method: 'POST',
    body: { ...faultPayload(input), discovery_time: new Date().toISOString() },
  })
  if (input.assignedToId) {
    dto = await apiRequest<FaultDto>(`/faults/${dto.id}/investigate/`, {
      method: 'POST',
      body: { assigned_engineer: input.assignedToId },
    })
  }
  return faultFromDto(dto)
}

export async function updateFault(id: string, input: Partial<FaultInput>): Promise<Fault> {
  return faultFromDto(
    await apiRequest<FaultDto>(`/faults/${id}/`, {
      method: 'PATCH',
      body: faultPayload(input),
    }),
  )
}

export async function investigateFault(id: string, assignedToId?: string | null): Promise<Fault> {
  return faultFromDto(
    await apiRequest<FaultDto>(`/faults/${id}/investigate/`, {
      method: 'POST',
      body: { assigned_engineer: assignedToId ?? null },
    }),
  )
}

export async function resolveFault(
  id: string,
  rootCause: string,
  resolution: string,
): Promise<Fault> {
  return faultFromDto(
    await apiRequest<FaultDto>(`/faults/${id}/resolve/`, {
      method: 'POST',
      body: { root_cause: rootCause, resolution },
    }),
  )
}

export async function closeFault(id: string): Promise<Fault> {
  return faultFromDto(await apiRequest<FaultDto>(`/faults/${id}/close/`, { method: 'POST' }))
}

export async function setFaultStatus(id: string, status: Fault['status']): Promise<Fault> {
  if (status === 'investigating') return investigateFault(id)
  if (status === 'closed') return closeFault(id)
  if (status === 'resolved') {
    unsupported('حل العطل يتطلب إدخال السبب الجذري ووصف الحل قبل استدعاء الإجراء المعتمد.')
  }
  return getFault(id)
}

export interface OperationsMonitoringDto {
  facility_count: number
  asset_count: number
  active_maintenance_orders: number
  open_faults: number
  open_incidents: number
}

export async function getOperationsMonitoring(): Promise<OperationsMonitoringDto> {
  return apiRequest<OperationsMonitoringDto>('/operations/monitoring/')
}
