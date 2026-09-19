import type { Asset, Facility, Fault, Priority, Severity, WorkOrder } from '@/types'

export interface FacilityDto {
  id: string
  created_from_project_id: string | null
  name: string
  type: Facility['type']
  location: string
  operation_start_date: string | null
  status: Facility['status']
  operations_manager_id: string | null
  asset_count?: number
  created_by_id: string
  created_at: string
  updated_at: string
}

export interface FacilityMonitoringDto {
  facility: FacilityDto
  asset_count: number
  asset_status_counts: Record<string, number>
  active_maintenance_orders: number
  open_faults: number
  open_incidents: number
}

export interface AssetDto {
  id: string
  facility_id: string
  facility_name: string
  name: string
  asset_type: string
  category: string
  serial_number: string
  manufacturer: string
  model: string
  location_inside_facility: string
  installation_date: string
  operation_date: string | null
  current_status: Asset['status']
  health_score: string | number
  remaining_useful_life: number | null
  last_maintenance_date: string | null
  notes: string
  created_by_id: string
  created_at: string
  updated_at: string
}

export interface MaintenanceOrderDto {
  id: string
  reference: string
  asset_id: string
  asset_name: string
  asset_type: string
  facility_id: string
  type: WorkOrder['maintenanceType']
  priority: 'low' | 'medium' | 'high' | 'urgent'
  description: string
  reason: string
  assigned_to_id: string | null
  expected_execution_date: string
  actual_completion_date: string | null
  execution_notes: string
  cancelled_at: string | null
  cancelled_by_id: string | null
  cancellation_reason: string
  status: WorkOrder['status']
  tasks: {
    id: string
    sequence: number
    label: string
    done: boolean
    completed_at: string | null
    completed_by_id: string | null
  }[]
  created_by_id: string
  created_at: string
  updated_at: string
}

export interface FaultDto {
  id: string
  reference: string
  asset_id: string
  asset_name: string
  facility_id: string
  fault_type: string
  description: string
  severity: 'minor' | 'moderate' | 'major' | 'critical'
  discovery_time: string
  reported_by_id: string | null
  assigned_engineer_id: string | null
  root_cause: string | null
  resolution: string | null
  resolved_at: string | null
  status: Fault['status']
  created_by_id: string
  created_at: string
  updated_at: string
}

const faultSeverityFromDto: Record<FaultDto['severity'], Severity> = {
  minor: 'low',
  moderate: 'medium',
  major: 'high',
  critical: 'critical',
}

export const faultSeverityToDto: Record<Severity, FaultDto['severity']> = {
  low: 'minor',
  medium: 'moderate',
  high: 'major',
  critical: 'critical',
}

const priorityFromDto: Record<MaintenanceOrderDto['priority'], Priority> = {
  low: 'low',
  medium: 'medium',
  high: 'high',
  urgent: 'critical',
}

export const priorityToDto: Record<Priority, MaintenanceOrderDto['priority']> = {
  low: 'low',
  medium: 'medium',
  high: 'high',
  critical: 'urgent',
}

function numberValue(value: string | number): number {
  return typeof value === 'number' ? value : Number(value)
}

export function facilityFromDto(dto: FacilityDto, assetCount = dto.asset_count ?? 0): Facility {
  return {
    id: dto.id,
    projectId: dto.created_from_project_id ?? '',
    name: dto.name,
    type: dto.type,
    location: dto.location,
    operationStartDate: dto.operation_start_date ?? dto.created_at,
    status: dto.status,
    assetCount,
    uptimePercent: null,
    operationsManagerId: dto.operations_manager_id,
  }
}

export function assetFromDto(dto: AssetDto, faultCount = 0): Asset {
  return {
    id: dto.id,
    facilityId: dto.facility_id,
    name: dto.name,
    assetType: dto.asset_type,
    category: dto.category,
    locationInFacility: dto.location_inside_facility,
    serialNumber: dto.serial_number,
    installDate: dto.installation_date,
    commissionDate: dto.operation_date,
    status: dto.current_status,
    notes: dto.notes,
    manufacturer: dto.manufacturer,
    model: dto.model,
    remainingUsefulLife: dto.remaining_useful_life,
    createdById: dto.created_by_id,
    createdAt: dto.created_at,
    healthScore: numberValue(dto.health_score),
    lastMaintenanceAt: dto.last_maintenance_date,
    faultCount,
    updatedAt: dto.updated_at,
  }
}

export function workOrderFromDto(dto: MaintenanceOrderDto): WorkOrder {
  return {
    id: dto.id,
    reference: dto.reference,
    assetId: dto.asset_id,
    assetType: dto.asset_type,
    facilityId: dto.facility_id,
    maintenanceType: dto.type,
    reason: dto.reason,
    description: dto.description,
    priority: priorityFromDto[dto.priority],
    status: dto.status,
    scheduledDate: dto.expected_execution_date,
    completedDate: dto.actual_completion_date,
    assignedToId: dto.assigned_to_id,
    notes: dto.execution_notes,
    tasks: dto.tasks.map((task) => ({
      id: task.id,
      sequence: task.sequence,
      label: task.label,
      done: task.done,
      completedAt: task.completed_at,
      completedById: task.completed_by_id,
    })),
    cancelledAt: dto.cancelled_at,
    cancelledById: dto.cancelled_by_id,
    cancellationReason: dto.cancellation_reason,
    createdAt: dto.created_at,
  }
}

export function faultFromDto(dto: FaultDto): Fault {
  return {
    id: dto.id,
    reference: dto.reference,
    assetId: dto.asset_id,
    facilityId: dto.facility_id,
    faultType: dto.fault_type,
    description: dto.description,
    severity: faultSeverityFromDto[dto.severity],
    rootCause: dto.root_cause,
    resolution: dto.resolution,
    status: dto.status,
    assignedToId: dto.assigned_engineer_id,
    discoveredAt: dto.discovery_time,
    resolvedAt: dto.resolved_at,
  }
}
