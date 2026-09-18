import type {
  AuthorizedVehicle,
  BoundingBox,
  CameraAiModel,
  CameraAiModelIdentifier,
  CameraEvent,
  CameraEventType,
  CameraRoi,
  PixelPoint,
  RestrictedZoneSchedule,
  VirtualLine,
} from '@/types'
import { apiRequest, downloadProtectedFile, fetchAllPages, saveDownloadedFile } from './client'

interface CameraEventDto {
  id: string
  event_type: CameraEventType
  camera_id: string
  camera_code: string
  facility_id: string
  facility_name: string
  roi_id: string | null
  roi_identifier: string | null
  track_id: string | null
  confidence: string | number | null
  object_class: string | null
  detected_at: string
  confirmed_at: string | null
  duration_seconds: string | number | null
  bbox: BoundingBox | null
  bbox_plate: BoundingBox | null
  bbox_vehicle: BoundingBox | null
  crossing_centroid: PixelPoint | null
  entered_roi_at: string | null
  time_restricted: boolean | null
  plate_number: string | null
  plate_confidence: string | number | null
  ocr_confidence: string | number | null
  vehicle_type: CameraEvent['vehicleType']
  vehicle_confidence: string | number | null
  direction: CameraEvent['direction']
  authorized: boolean | null
  tamper_type: CameraEvent['tamperType']
  status: CameraEvent['status']
  security_alert_id: string | null
  snapshot_available: boolean
  snapshot_download_url: string | null
  created_at: string
  updated_at: string
}

const decimal = (value: string | number | null): number | null =>
  value === null ? null : Number(value)

export const cameraEventFromDto = (dto: CameraEventDto): CameraEvent => ({
  id: dto.id,
  eventType: dto.event_type,
  cameraId: dto.camera_id,
  cameraCode: dto.camera_code,
  facilityId: dto.facility_id,
  facilityName: dto.facility_name,
  roiId: dto.roi_id,
  roiIdentifier: dto.roi_identifier,
  trackId: dto.track_id,
  confidence: decimal(dto.confidence),
  objectClass: dto.object_class,
  detectedAt: dto.detected_at,
  confirmedAt: dto.confirmed_at,
  durationSeconds: decimal(dto.duration_seconds),
  bbox: dto.bbox,
  bboxPlate: dto.bbox_plate,
  bboxVehicle: dto.bbox_vehicle,
  crossingCentroid: dto.crossing_centroid,
  enteredRoiAt: dto.entered_roi_at,
  timeRestricted: dto.time_restricted,
  plateNumber: dto.plate_number,
  plateConfidence: decimal(dto.plate_confidence),
  ocrConfidence: decimal(dto.ocr_confidence),
  vehicleType: dto.vehicle_type,
  vehicleConfidence: decimal(dto.vehicle_confidence),
  direction: dto.direction,
  authorized: dto.authorized,
  tamperType: dto.tamper_type,
  status: dto.status,
  securityAlertId: dto.security_alert_id,
  snapshotAvailable: dto.snapshot_available,
  snapshotDownloadUrl: dto.snapshot_download_url,
  createdAt: dto.created_at,
  updatedAt: dto.updated_at,
})

export interface CameraEventFilters {
  camera?: string
  eventType?: CameraEventType
  detectedAfter?: string
  detectedBefore?: string
  plateNumber?: string
  authorized?: boolean
}

export async function listCameraEvents(filters: CameraEventFilters = {}): Promise<CameraEvent[]> {
  const query = new URLSearchParams()
  if (filters.camera) query.set('camera', filters.camera)
  if (filters.eventType) query.set('event_type', filters.eventType)
  if (filters.detectedAfter) query.set('detected_at__gte', filters.detectedAfter)
  if (filters.detectedBefore) query.set('detected_at__lte', filters.detectedBefore)
  if (filters.plateNumber) query.set('plate_number', filters.plateNumber)
  if (filters.authorized !== undefined) query.set('authorized', String(filters.authorized))
  const suffix = query.size ? `?${query}` : ''
  return (await fetchAllPages<CameraEventDto>(`/camera-events/${suffix}`)).map(cameraEventFromDto)
}

export async function getCameraEvent(id: string): Promise<CameraEvent> {
  return cameraEventFromDto(await apiRequest<CameraEventDto>(`/camera-events/${id}/`))
}

export async function downloadCameraEventSnapshot(id: string): Promise<void> {
  saveDownloadedFile(
    await downloadProtectedFile(`/camera-events/${id}/snapshot/`, `camera-event-${id}`),
  )
}

interface CameraRoiDto {
  id: string
  camera_id: string
  identifier: string
  name: string
  polygon: PixelPoint[]
  is_active: boolean
}

const roiFromDto = (dto: CameraRoiDto): CameraRoi => ({
  id: dto.id,
  cameraId: dto.camera_id,
  identifier: dto.identifier,
  name: dto.name,
  polygon: dto.polygon,
  isActive: dto.is_active,
})

export async function listCameraRois(cameraId?: string): Promise<CameraRoi[]> {
  const query = cameraId ? `?camera_id=${encodeURIComponent(cameraId)}` : ''
  return (await fetchAllPages<CameraRoiDto>(`/roi/${query}`)).map(roiFromDto)
}

export async function createCameraRoi(input: {
  camera: string
  identifier: string
  name: string
  polygon: PixelPoint[]
}): Promise<CameraRoi> {
  return roiFromDto(await apiRequest<CameraRoiDto>('/roi/', { method: 'POST', body: input }))
}

export async function updateCameraRoi(
  id: string,
  input: Partial<Pick<CameraRoi, 'name' | 'polygon'>>,
): Promise<CameraRoi> {
  return roiFromDto(await apiRequest<CameraRoiDto>(`/roi/${id}/`, { method: 'PATCH', body: input }))
}

export const disableCameraRoi = (id: string) =>
  apiRequest<void>(`/roi/${id}/`, { method: 'DELETE' })

interface ScheduleDto {
  id: string
  roi_id: string
  camera_id: string
  always_restricted: boolean
  from_time: string | null
  to_time: string | null
  days_of_week: number[]
  timezone_name: string
  crosses_midnight: boolean
  is_active: boolean
}

const scheduleFromDto = (dto: ScheduleDto): RestrictedZoneSchedule => ({
  id: dto.id,
  roiId: dto.roi_id,
  cameraId: dto.camera_id,
  alwaysRestricted: dto.always_restricted,
  fromTime: dto.from_time,
  toTime: dto.to_time,
  daysOfWeek: dto.days_of_week,
  timezoneName: dto.timezone_name,
  crossesMidnight: dto.crosses_midnight,
  isActive: dto.is_active,
})

export async function listRestrictedSchedules(
  cameraId?: string,
): Promise<RestrictedZoneSchedule[]> {
  const query = cameraId ? `?camera_id=${encodeURIComponent(cameraId)}` : ''
  return (await fetchAllPages<ScheduleDto>(`/restricted-schedules/${query}`)).map(scheduleFromDto)
}

const scheduleBody = (input: {
  roiId?: string
  alwaysRestricted: boolean
  fromTime: string | null
  toTime: string | null
  daysOfWeek: number[]
  timezoneName: string
}) => ({
  ...(input.roiId ? { roi: input.roiId } : {}),
  always_restricted: input.alwaysRestricted,
  from_time: input.fromTime,
  to_time: input.toTime,
  days_of_week: input.daysOfWeek,
  timezone_name: input.timezoneName,
})

export async function createRestrictedSchedule(
  input: Parameters<typeof scheduleBody>[0] & { roiId: string },
): Promise<RestrictedZoneSchedule> {
  return scheduleFromDto(
    await apiRequest<ScheduleDto>('/restricted-schedules/', {
      method: 'POST',
      body: scheduleBody(input),
    }),
  )
}

export async function updateRestrictedSchedule(
  id: string,
  input: Parameters<typeof scheduleBody>[0],
): Promise<RestrictedZoneSchedule> {
  return scheduleFromDto(
    await apiRequest<ScheduleDto>(`/restricted-schedules/${id}/`, {
      method: 'PATCH',
      body: scheduleBody(input),
    }),
  )
}

export const disableRestrictedSchedule = (id: string) =>
  apiRequest<void>(`/restricted-schedules/${id}/`, { method: 'DELETE' })

interface VirtualLineDto {
  id: string
  camera_id: string
  line_start: PixelPoint
  line_end: PixelPoint
  is_active: boolean
}

const lineFromDto = (dto: VirtualLineDto): VirtualLine => ({
  id: dto.id,
  cameraId: dto.camera_id,
  lineStart: dto.line_start,
  lineEnd: dto.line_end,
  isActive: dto.is_active,
})

export async function listVirtualLines(cameraId?: string): Promise<VirtualLine[]> {
  const query = cameraId ? `?camera_id=${encodeURIComponent(cameraId)}` : ''
  return (await fetchAllPages<VirtualLineDto>(`/virtual-lines/${query}`)).map(lineFromDto)
}

export async function createVirtualLine(input: {
  camera: string
  lineStart: PixelPoint
  lineEnd: PixelPoint
}): Promise<VirtualLine> {
  return lineFromDto(
    await apiRequest<VirtualLineDto>('/virtual-lines/', {
      method: 'POST',
      body: { camera: input.camera, line_start: input.lineStart, line_end: input.lineEnd },
    }),
  )
}

export async function updateVirtualLine(
  id: string,
  input: Pick<VirtualLine, 'lineStart' | 'lineEnd'>,
): Promise<VirtualLine> {
  return lineFromDto(
    await apiRequest<VirtualLineDto>(`/virtual-lines/${id}/`, {
      method: 'PATCH',
      body: { line_start: input.lineStart, line_end: input.lineEnd },
    }),
  )
}

export const disableVirtualLine = (id: string) =>
  apiRequest<void>(`/virtual-lines/${id}/`, { method: 'DELETE' })

interface AuthorizedVehicleDto {
  id: string
  plate_number: string
  responsible_name: string
  expires_on: string | null
  currently_authorized: boolean
  is_active: boolean
}

const vehicleFromDto = (dto: AuthorizedVehicleDto): AuthorizedVehicle => ({
  id: dto.id,
  plateNumber: dto.plate_number,
  responsibleName: dto.responsible_name,
  expiresOn: dto.expires_on,
  currentlyAuthorized: dto.currently_authorized,
  isActive: dto.is_active,
})

export async function listAuthorizedVehicles(): Promise<AuthorizedVehicle[]> {
  return (await fetchAllPages<AuthorizedVehicleDto>('/vehicles/authorized/')).map(vehicleFromDto)
}

export async function createAuthorizedVehicle(input: {
  plateNumber: string
  responsibleName: string
  expiresOn: string | null
}): Promise<AuthorizedVehicle> {
  return vehicleFromDto(
    await apiRequest<AuthorizedVehicleDto>('/vehicles/authorized/', {
      method: 'POST',
      body: {
        plate_number: input.plateNumber,
        responsible_name: input.responsibleName,
        expires_on: input.expiresOn,
      },
    }),
  )
}

export async function updateAuthorizedVehicle(
  id: string,
  input: { plateNumber: string; responsibleName: string; expiresOn: string | null },
): Promise<AuthorizedVehicle> {
  return vehicleFromDto(
    await apiRequest<AuthorizedVehicleDto>(`/vehicles/authorized/${id}/`, {
      method: 'PATCH',
      body: {
        plate_number: input.plateNumber,
        responsible_name: input.responsibleName,
        expires_on: input.expiresOn,
      },
    }),
  )
}

export const disableAuthorizedVehicle = (id: string) =>
  apiRequest<void>(`/vehicles/authorized/${id}/`, { method: 'DELETE' })

interface CameraAiModelDto {
  id: string
  camera_id: string
  model_identifier: CameraAiModelIdentifier
  is_active: boolean
  updated_at: string
}

const modelFromDto = (dto: CameraAiModelDto): CameraAiModel => ({
  id: dto.id,
  cameraId: dto.camera_id,
  modelIdentifier: dto.model_identifier,
  isActive: dto.is_active,
  updatedAt: dto.updated_at,
})

export async function listCameraAiModels(cameraId: string): Promise<CameraAiModel[]> {
  return (await apiRequest<CameraAiModelDto[]>(`/cameras/${cameraId}/active-models/`)).map(
    modelFromDto,
  )
}

export async function enableCameraAiModel(
  cameraId: string,
  modelIdentifier: CameraAiModelIdentifier,
): Promise<CameraAiModel> {
  return modelFromDto(
    await apiRequest<CameraAiModelDto>(`/cameras/${cameraId}/active-models/`, {
      method: 'POST',
      body: { model_identifier: modelIdentifier },
    }),
  )
}

export const disableCameraAiModel = (cameraId: string, modelIdentifier: CameraAiModelIdentifier) =>
  apiRequest<void>(`/cameras/${cameraId}/active-models/${modelIdentifier}/`, {
    method: 'DELETE',
  })
