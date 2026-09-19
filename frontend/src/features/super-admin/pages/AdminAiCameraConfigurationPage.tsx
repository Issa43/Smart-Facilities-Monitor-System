import { useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { CameraAiModelIdentifier, PixelPoint } from '@/types'
import {
  createAuthorizedVehicle,
  createCameraRoi,
  createRestrictedSchedule,
  createVirtualLine,
  disableAuthorizedVehicle,
  disableCameraAiModel,
  disableCameraRoi,
  disableRestrictedSchedule,
  disableVirtualLine,
  enableCameraAiModel,
  listAuthorizedVehicles,
  listCameraAiModels,
  listCameraRois,
  listRestrictedSchedules,
  listVirtualLines,
} from '@/api/aiSecurity'
import { listCameras } from '@/api/security'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { Switch } from '@/components/ui/Controls/Controls'
import { ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { Panel } from '@/components/ui/Panel/Panel'
import { Section, SplitGrid } from '@/components/ui/Display/Display'

const MODEL_LABELS: Record<CameraAiModelIdentifier, string> = {
  fire_smoke: 'الحريق والدخان',
  intrusion: 'التسلل',
  anpr: 'قراءة اللوحات',
  tamper: 'العبث بالكاميرا',
}
const MODEL_IDS = Object.keys(MODEL_LABELS) as CameraAiModelIdentifier[]
const parsePoints = (value: string): PixelPoint[] => JSON.parse(value) as PixelPoint[]

export function AdminAiCameraConfigurationPage() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [cameraId, setCameraId] = useState('')
  const [roi, setRoi] = useState({
    identifier: '',
    name: '',
    polygon: '[{"x":0,"y":0},{"x":100,"y":0},{"x":0,"y":100}]',
  })
  const [line, setLine] = useState({ start: '{"x":0,"y":50}', end: '{"x":100,"y":50}' })
  const [vehicle, setVehicle] = useState({ plate: '', responsible: '', expires: '' })
  const [scheduleRoi, setScheduleRoi] = useState('')
  const cameras = useQuery({ queryKey: ['security-cameras'], queryFn: listCameras })
  const selectedCamera = cameraId || cameras.data?.[0]?.id || ''
  const rois = useQuery({
    queryKey: ['camera-rois', selectedCamera],
    queryFn: () => listCameraRois(selectedCamera),
    enabled: Boolean(selectedCamera),
  })
  const schedules = useQuery({
    queryKey: ['restricted-schedules', selectedCamera],
    queryFn: () => listRestrictedSchedules(selectedCamera),
    enabled: Boolean(selectedCamera),
  })
  const lines = useQuery({
    queryKey: ['virtual-lines', selectedCamera],
    queryFn: () => listVirtualLines(selectedCamera),
    enabled: Boolean(selectedCamera),
  })
  const vehicles = useQuery({ queryKey: ['authorized-vehicles'], queryFn: listAuthorizedVehicles })
  const models = useQuery({
    queryKey: ['camera-models', selectedCamera],
    queryFn: () => listCameraAiModels(selectedCamera),
    enabled: Boolean(selectedCamera),
  })
  const queries = [cameras, rois, schedules, lines, vehicles, models]
  const refresh = () =>
    queryClient.invalidateQueries({
      predicate: (query) =>
        [
          'camera-rois',
          'restricted-schedules',
          'virtual-lines',
          'authorized-vehicles',
          'camera-models',
        ].includes(String(query.queryKey[0])),
    })
  const feedback = (title: string) => ({
    onSuccess: () => {
      refresh()
      showToast({ tone: 'success' as const, title })
    },
    onError: (error: Error) =>
      showToast({
        tone: 'critical' as const,
        title: 'تعذّر حفظ الإعداد',
        description: error.message,
      }),
  })
  const addRoi = useMutation({
    mutationFn: () =>
      createCameraRoi({
        camera: selectedCamera,
        identifier: roi.identifier.trim(),
        name: roi.name.trim(),
        polygon: parsePoints(roi.polygon),
      }),
    ...feedback('تمت إضافة ROI'),
  })
  const addLine = useMutation({
    mutationFn: () =>
      createVirtualLine({
        camera: selectedCamera,
        lineStart: JSON.parse(line.start),
        lineEnd: JSON.parse(line.end),
      }),
    ...feedback('تمت إضافة الخط الافتراضي'),
  })
  const addVehicle = useMutation({
    mutationFn: () =>
      createAuthorizedVehicle({
        plateNumber: vehicle.plate,
        responsibleName: vehicle.responsible,
        expiresOn: vehicle.expires || null,
      }),
    ...feedback('تمت إضافة المركبة المصرّح بها'),
  })
  const addSchedule = useMutation({
    mutationFn: () =>
      createRestrictedSchedule({
        roiId: scheduleRoi,
        alwaysRestricted: true,
        fromTime: null,
        toTime: null,
        daysOfWeek: [],
        timezoneName: 'UTC',
      }),
    ...feedback('تمت إضافة الجدول المقيّد'),
  })
  const toggleModel = useMutation({
    mutationFn: async ({ id, active }: { id: CameraAiModelIdentifier; active: boolean }) => {
      if (active) await enableCameraAiModel(selectedCamera, id)
      else await disableCameraAiModel(selectedCamera, id)
    },
    ...feedback('تم تحديث النماذج الفعالة'),
  })
  const disable = useMutation({
    mutationFn: ({ kind, id }: { kind: string; id: string }) =>
      kind === 'roi'
        ? disableCameraRoi(id)
        : kind === 'schedule'
          ? disableRestrictedSchedule(id)
          : kind === 'line'
            ? disableVirtualLine(id)
            : disableAuthorizedVehicle(id),
    ...feedback('تم تعطيل الإعداد مع حفظ السجل التاريخي'),
  })
  const activeModels = useMemo(
    () =>
      new Set(
        (models.data ?? []).filter((model) => model.isActive).map((model) => model.modelIdentifier),
      ),
    [models.data],
  )

  if (queries.some((query) => query.isError))
    return <ErrorState error={queries.find((query) => query.isError)?.error} />
  return (
    <>
      <PageHeader
        title="تهيئة تكامل كاميرات الذكاء الاصطناعي"
        description="إعدادات بشرية بإدارة Super Admin فقط. لا تتضمن استدلالاً أو مفاتيح آلة أو بث فيديو."
      />
      <Section>
        <Panel title="الكاميرا">
          {cameras.isPending ? (
            <SkeletonLines count={2} />
          ) : !cameras.data?.length ? (
            <StateCard bare title="لا توجد كاميرات قابلة للتهيئة" />
          ) : (
            <select
              aria-label="الكاميرا"
              value={selectedCamera}
              onChange={(event) => setCameraId(event.target.value)}
            >
              {cameras.data.map((camera) => (
                <option key={camera.id} value={camera.id}>
                  {camera.code} — {camera.name}
                </option>
              ))}
            </select>
          )}
        </Panel>
      </Section>
      {selectedCamera && (
        <>
          <Section>
            <Panel
              title="النماذج الفعالة"
              subtitle="يضبط هذا عقد التكامل ولا يشغّل نموذجاً داخل SFLMS."
            >
              <div style={{ display: 'grid', gap: 12 }}>
                {MODEL_IDS.map((id) => (
                  <label key={id} style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>{MODEL_LABELS[id]}</span>
                    <Switch
                      checked={activeModels.has(id)}
                      disabled={toggleModel.isPending}
                      label={`تفعيل ${MODEL_LABELS[id]}`}
                      onChange={(active) => toggleModel.mutate({ id, active })}
                    />
                  </label>
                ))}
              </div>
            </Panel>
          </Section>
          <SplitGrid>
            <Panel title="مناطق ROI">
              <ConfigList
                items={rois.data?.map((item) => ({
                  id: item.id,
                  label: `${item.identifier} — ${item.name}`,
                  active: item.isActive,
                }))}
                loading={rois.isPending}
                onDisable={(id) => disable.mutate({ kind: 'roi', id })}
              />
              <ConfigForm
                onSubmit={() => addRoi.mutate()}
                disabled={!roi.identifier.trim() || !roi.name.trim()}
              >
                <input
                  aria-label="معرّف ROI"
                  placeholder="identifier"
                  value={roi.identifier}
                  onChange={(event) => setRoi({ ...roi, identifier: event.target.value })}
                />
                <input
                  aria-label="اسم ROI"
                  placeholder="الاسم"
                  value={roi.name}
                  onChange={(event) => setRoi({ ...roi, name: event.target.value })}
                />
                <textarea
                  aria-label="Polygon JSON"
                  value={roi.polygon}
                  onChange={(event) => setRoi({ ...roi, polygon: event.target.value })}
                />
              </ConfigForm>
            </Panel>
            <Panel title="الخطوط الافتراضية">
              <ConfigList
                items={lines.data?.map((item) => ({
                  id: item.id,
                  label: `${JSON.stringify(item.lineStart)} → ${JSON.stringify(item.lineEnd)}`,
                  active: item.isActive,
                }))}
                loading={lines.isPending}
                onDisable={(id) => disable.mutate({ kind: 'line', id })}
              />
              <ConfigForm onSubmit={() => addLine.mutate()}>
                <input
                  aria-label="بداية الخط JSON"
                  value={line.start}
                  onChange={(event) => setLine({ ...line, start: event.target.value })}
                />
                <input
                  aria-label="نهاية الخط JSON"
                  value={line.end}
                  onChange={(event) => setLine({ ...line, end: event.target.value })}
                />
              </ConfigForm>
            </Panel>
            <Panel title="الجداول المقيّدة دائماً">
              <ConfigList
                items={schedules.data?.map((item) => ({
                  id: item.id,
                  label: `${item.roiId} — ${item.timezoneName}`,
                  active: item.isActive,
                }))}
                loading={schedules.isPending}
                onDisable={(id) => disable.mutate({ kind: 'schedule', id })}
              />
              <ConfigForm onSubmit={() => addSchedule.mutate()} disabled={!scheduleRoi}>
                <select
                  aria-label="ROI للجدول"
                  value={scheduleRoi}
                  onChange={(event) => setScheduleRoi(event.target.value)}
                >
                  <option value="">اختر ROI</option>
                  {rois.data
                    ?.filter((item) => item.isActive)
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                </select>
              </ConfigForm>
            </Panel>
            <Panel title="المركبات المصرّح بها">
              <ConfigList
                items={vehicles.data?.map((item) => ({
                  id: item.id,
                  label: `${item.plateNumber} — ${item.responsibleName}`,
                  active: item.isActive && item.currentlyAuthorized,
                }))}
                loading={vehicles.isPending}
                onDisable={(id) => disable.mutate({ kind: 'vehicle', id })}
              />
              <ConfigForm
                onSubmit={() => addVehicle.mutate()}
                disabled={!vehicle.plate.trim() || !vehicle.responsible.trim()}
              >
                <input
                  aria-label="رقم اللوحة"
                  placeholder="رقم اللوحة"
                  value={vehicle.plate}
                  onChange={(event) => setVehicle({ ...vehicle, plate: event.target.value })}
                />
                <input
                  aria-label="المسؤول"
                  placeholder="المسؤول"
                  value={vehicle.responsible}
                  onChange={(event) => setVehicle({ ...vehicle, responsible: event.target.value })}
                />
                <input
                  aria-label="تاريخ الانتهاء"
                  type="date"
                  value={vehicle.expires}
                  onChange={(event) => setVehicle({ ...vehicle, expires: event.target.value })}
                />
              </ConfigForm>
            </Panel>
          </SplitGrid>
        </>
      )}
    </>
  )
}

function ConfigList({
  items,
  loading,
  onDisable,
}: {
  items?: { id: string; label: string; active: boolean }[]
  loading: boolean
  onDisable: (id: string) => void
}) {
  if (loading) return <SkeletonLines count={3} />
  if (!items?.length) return <StateCard bare title="لا توجد إعدادات" />
  return (
    <div style={{ display: 'grid', gap: 8, marginBottom: 16 }}>
      {items.map((item) => (
        <div
          key={item.id}
          style={{ display: 'flex', gap: 8, justifyContent: 'space-between', alignItems: 'center' }}
        >
          <span>
            {item.label}{' '}
            <Badge tone={item.active ? 'success' : 'neutral'}>
              {item.active ? 'فعال' : 'معطل'}
            </Badge>
          </span>
          {item.active && (
            <Button size="sm" variant="ghost" onClick={() => onDisable(item.id)}>
              تعطيل
            </Button>
          )}
        </div>
      ))}
    </div>
  )
}

function ConfigForm({
  children,
  onSubmit,
  disabled,
}: {
  children: ReactNode
  onSubmit: () => void
  disabled?: boolean
}) {
  return (
    <form
      style={{ display: 'grid', gap: 8 }}
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}
    >
      {children}
      <Button type="submit" disabled={disabled}>
        إضافة
      </Button>
    </form>
  )
}
