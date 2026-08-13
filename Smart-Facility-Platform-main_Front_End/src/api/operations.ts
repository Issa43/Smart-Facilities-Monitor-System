import type { Asset, Facility, Fault, Priority, WorkOrder } from '@/types'
import type { Database } from './fixtures'
import { delay, newId, notFound, nowIso } from './client'
import { clone, commit, getDb } from './db'

/* ==========================================================================
   Facilities
   ========================================================================== */

export async function listFacilities(): Promise<Facility[]> {
  await delay()
  return clone(getDb().facilities)
}

export async function getFacility(id: string): Promise<Facility> {
  await delay()
  const facility = getDb().facilities.find((f) => f.id === id)
  return facility ? clone(facility) : notFound('المنشأة')
}

/* ==========================================================================
   Assets
   ========================================================================== */

export interface AssetInput {
  facilityId: string
  name: string
  category: Asset['category']
  locationInFacility: string
  serialNumber: string
  installDate: string
  commissionDate: string
  status: Asset['status']
  notes: string
}

export async function listAssets(facilityId?: string): Promise<Asset[]> {
  await delay()
  const all = getDb().assets
  return clone(facilityId ? all.filter((a) => a.facilityId === facilityId) : all)
}

export async function getAsset(id: string): Promise<Asset> {
  await delay()
  const asset = getDb().assets.find((a) => a.id === id)
  return asset ? clone(asset) : notFound('الأصل')
}

export async function createAsset(input: AssetInput): Promise<Asset> {
  await delay()
  return commit((db) => {
    const asset: Asset = {
      id: newId('ast'),
      ...input,
      healthScore: 100,
      lastMaintenanceAt: null,
      faultCount: 0,
      updatedAt: nowIso(),
    }
    db.assets.push(asset)
    syncFacilityAssetCount(db, input.facilityId)
    return clone(asset)
  })
}

export async function updateAsset(id: string, input: Partial<AssetInput>): Promise<Asset> {
  await delay()
  return commit((db) => {
    const asset = db.assets.find((a) => a.id === id)
    if (!asset) notFound('الأصل')
    Object.assign(asset, input, { updatedAt: nowIso() })
    return clone(asset)
  })
}

export async function deleteAsset(id: string): Promise<void> {
  await delay()
  commit((db) => {
    const asset = db.assets.find((a) => a.id === id)
    if (!asset) notFound('الأصل')
    const { facilityId } = asset
    db.assets = db.assets.filter((a) => a.id !== id)
    syncFacilityAssetCount(db, facilityId)
  })
}

function syncFacilityAssetCount(db: Database, facilityId: string): void {
  const facility = db.facilities.find((f) => f.id === facilityId)
  if (facility) facility.assetCount = db.assets.filter((a) => a.facilityId === facilityId).length
}

/* ==========================================================================
   Work orders
   ========================================================================== */

export interface WorkOrderInput {
  assetId: string
  facilityId: string
  maintenanceType: WorkOrder['maintenanceType']
  reason: string
  description: string
  priority: Priority
  scheduledDate: string
  assignedToId: string | null
}

export async function listWorkOrders(facilityId?: string): Promise<WorkOrder[]> {
  await delay()
  const all = getDb().workOrders
  return clone(facilityId ? all.filter((w) => w.facilityId === facilityId) : all)
}

export async function getWorkOrder(id: string): Promise<WorkOrder> {
  await delay()
  const order = getDb().workOrders.find((w) => w.id === id)
  return order ? clone(order) : notFound('أمر الصيانة')
}

export async function createWorkOrder(input: WorkOrderInput): Promise<WorkOrder> {
  await delay()
  return commit((db) => {
    const order: WorkOrder = {
      id: newId('wor'),
      reference: `WO-${new Date().getFullYear()}-${String(db.workOrders.length + 1).padStart(4, '0')}`,
      ...input,
      status: 'open',
      completedDate: null,
      notes: '',
      tasks: [],
      createdAt: nowIso(),
    }
    db.workOrders.unshift(order)
    return clone(order)
  })
}

export async function updateWorkOrder(
  id: string,
  input: Partial<WorkOrderInput> & { notes?: string },
): Promise<WorkOrder> {
  await delay()
  return commit((db) => {
    const order = db.workOrders.find((w) => w.id === id)
    if (!order) notFound('أمر الصيانة')
    Object.assign(order, input)
    return clone(order)
  })
}

export async function setWorkOrderStatus(
  id: string,
  status: WorkOrder['status'],
): Promise<WorkOrder> {
  await delay(300)
  return commit((db) => {
    const order = db.workOrders.find((w) => w.id === id)
    if (!order) notFound('أمر الصيانة')

    order.status = status

    if (status === 'completed') {
      order.completedDate = nowIso()
      // Closing a work order is what refreshes the asset's health and last-service date.
      const asset = db.assets.find((a) => a.id === order.assetId)
      if (asset) {
        asset.lastMaintenanceAt = nowIso()
        asset.healthScore = Math.min(100, asset.healthScore + 12)
        asset.status = 'operational'
        asset.updatedAt = nowIso()
      }
    }

    return clone(order)
  })
}

export async function toggleWorkOrderTask(orderId: string, taskId: string): Promise<WorkOrder> {
  await delay(120)
  return commit((db) => {
    const order = db.workOrders.find((w) => w.id === orderId)
    if (!order) notFound('أمر الصيانة')
    const task = order.tasks.find((t) => t.id === taskId)
    if (task) task.done = !task.done
    return clone(order)
  })
}

/* ==========================================================================
   Faults
   ========================================================================== */

export interface FaultInput {
  assetId: string
  facilityId: string
  faultType: string
  description: string
  severity: Fault['severity']
  assignedToId: string | null
}

export async function listFaults(facilityId?: string): Promise<Fault[]> {
  await delay()
  const all = getDb().faults
  return clone(facilityId ? all.filter((f) => f.facilityId === facilityId) : all)
}

export async function getFault(id: string): Promise<Fault> {
  await delay()
  const fault = getDb().faults.find((f) => f.id === id)
  return fault ? clone(fault) : notFound('العطل')
}

export async function createFault(input: FaultInput): Promise<Fault> {
  await delay()
  return commit((db) => {
    const fault: Fault = {
      id: newId('flt'),
      reference: `FLT-${new Date().getFullYear()}-${String(db.faults.length + 1).padStart(4, '0')}`,
      ...input,
      rootCause: null,
      status: 'reported',
      discoveredAt: nowIso(),
      resolvedAt: null,
    }
    db.faults.unshift(fault)

    // Recording a fault degrades the asset — that is the point of tracking them.
    const asset = db.assets.find((a) => a.id === input.assetId)
    if (asset) {
      asset.faultCount += 1
      asset.healthScore = Math.max(0, asset.healthScore - (input.severity === 'critical' ? 25 : 10))
      asset.status = input.severity === 'critical' ? 'out_of_service' : 'needs_maintenance'
      asset.updatedAt = nowIso()
    }

    return clone(fault)
  })
}

export async function updateFault(
  id: string,
  input: Partial<FaultInput> & { rootCause?: string | null },
): Promise<Fault> {
  await delay()
  return commit((db) => {
    const fault = db.faults.find((f) => f.id === id)
    if (!fault) notFound('العطل')
    Object.assign(fault, input)
    return clone(fault)
  })
}

export async function setFaultStatus(id: string, status: Fault['status']): Promise<Fault> {
  await delay(300)
  return commit((db) => {
    const fault = db.faults.find((f) => f.id === id)
    if (!fault) notFound('العطل')

    fault.status = status
    if (status === 'resolved') {
      fault.resolvedAt = nowIso()
      const asset = db.assets.find((a) => a.id === fault.assetId)
      if (asset) {
        asset.status = 'operational'
        asset.healthScore = Math.min(100, asset.healthScore + 15)
        asset.updatedAt = nowIso()
      }
    }

    return clone(fault)
  })
}
