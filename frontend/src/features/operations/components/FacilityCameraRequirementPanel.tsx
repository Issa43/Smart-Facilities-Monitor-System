import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { FacilityCamera, FacilityCameraRequirement } from '@/types'
import { formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { getFacilityCameraRequirement, setFacilityCameraRequirement } from '@/api/operations'
import { useToast } from '@/context/ToastContext'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { DescriptionList } from '@/components/ui/Display/Display'
import { Alert, ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { Field } from '@/components/ui/Field/Field'
import { Panel } from '@/components/ui/Panel/Panel'
import { MAX_REQUIRED_CAMERA_COUNT, validateRequiredCameraCount } from './cameraRequirement'

const CAMERA_STATUS_LABELS: Record<FacilityCamera['status'], string> = {
  online: 'متصلة',
  offline: 'غير متصلة',
  degraded: 'أداء منخفض',
  maintenance: 'تحت الصيانة',
}

const CAMERA_STATUS_TONE: Record<
  FacilityCamera['status'],
  'success' | 'neutral' | 'warning' | 'info'
> = {
  online: 'success',
  offline: 'neutral',
  degraded: 'warning',
  maintenance: 'info',
}

interface FacilityCameraRequirementPanelProps {
  facilityId: string
  /** The camera table is omitted where the host page is already dense. */
  showCameras?: boolean
}

/**
 * Required-camera editor shared by the Operations facility page and the Super
 * Admin projects page. Saving sends an absolute count: the server creates only
 * the missing cameras and never removes surplus ones.
 */
export function FacilityCameraRequirementPanel({
  facilityId,
  showCameras = true,
}: FacilityCameraRequirementPanelProps) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const queryKey = qk.facilities.cameraRequirement(facilityId)
  const requirementQuery = useQuery({
    queryKey,
    queryFn: () => getFacilityCameraRequirement(facilityId),
  })
  const [draft, setDraft] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)
  const [lastResult, setLastResult] = useState<FacilityCameraRequirement | null>(null)

  const save = useMutation({
    mutationFn: (count: number) => setFacilityCameraRequirement(facilityId, count),
    onSuccess: (result) => {
      queryClient.setQueryData(queryKey, result)
      queryClient.invalidateQueries({ queryKey: qk.facilities.all })
      queryClient.invalidateQueries({ queryKey: qk.assets.all })
      setDraft(null)
      setSubmitted(false)
      setLastResult(result)
      showToast({
        tone: 'success',
        title: 'تم حفظ عدد الكاميرات المطلوب',
        description:
          result.created > 0
            ? `أُضيفت ${formatNumber(result.created)} كاميرا جديدة.`
            : 'لم تكن هناك حاجة لإضافة كاميرات.',
      })
    },
    onError: (error) =>
      showToast({
        tone: 'critical',
        title: 'تعذّر حفظ عدد الكاميرات',
        description: error instanceof Error ? error.message : undefined,
      }),
  })

  if (requirementQuery.isError) return <ErrorState error={requirementQuery.error} />
  const requirement = requirementQuery.data
  if (requirementQuery.isPending || !requirement) {
    return (
      <Panel title="كاميرات المنشأة">
        <SkeletonLines count={3} />
      </Panel>
    )
  }

  const value =
    draft ??
    (requirement.requiredCameraCount === null ? '' : String(requirement.requiredCameraCount))
  const validationError = submitted ? validateRequiredCameraCount(value) : null
  const surplus =
    requirement.requiredCameraCount === null
      ? 0
      : Math.max(0, requirement.cameraCount - requirement.requiredCameraCount)

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmitted(true)
    if (validateRequiredCameraCount(value)) return
    save.mutate(Number(value.trim()))
  }

  return (
    <Panel title="كاميرات المنشأة">
      <form
        onSubmit={onSubmit}
        noValidate
        style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}
      >
        <Field
          label="عدد الكاميرات المطلوب"
          hint={`من 0 إلى ${formatNumber(MAX_REQUIRED_CAMERA_COUNT)}`}
          error={validationError ?? undefined}
        >
          {(props) => (
            <input
              {...props}
              type="number"
              inputMode="numeric"
              min={0}
              max={MAX_REQUIRED_CAMERA_COUNT}
              value={value}
              onChange={(event) => setDraft(event.target.value)}
            />
          )}
        </Field>
        <Button type="submit" loading={save.isPending}>
          حفظ
        </Button>
      </form>

      <div style={{ marginTop: 16 }}>
        <DescriptionList
          items={[
            {
              label: 'المطلوب',
              value:
                requirement.requiredCameraCount === null
                  ? 'غير محدد'
                  : formatNumber(requirement.requiredCameraCount),
            },
            { label: 'الكاميرات الحالية', value: formatNumber(requirement.cameraCount) },
            ...(lastResult
              ? [{ label: 'أُضيفت في آخر حفظ', value: formatNumber(lastResult.created) }]
              : []),
            { label: 'الفائض', value: formatNumber(surplus) },
          ]}
        />
      </div>

      {surplus > 0 && (
        <div style={{ marginTop: 16 }}>
          <Alert
            tone="warning"
            title={`${formatNumber(surplus)} كاميرا فائضة عن العدد المطلوب`}
            description="لا تُحذف الكاميرات تلقائياً حفاظاً على سجلها التشغيلي؛ يتم إخراجها من الخدمة يدوياً عند الحاجة."
          />
        </div>
      )}

      {showCameras && (
        <div style={{ marginTop: 16 }}>
          <DataTable
            rows={requirement.cameras}
            rowKey={(camera) => camera.id}
            columns={[
              {
                key: 'code',
                header: 'رمز الكاميرا',
                sortValue: (camera) => camera.code,
                render: (camera) => <span className="mono">{camera.code}</span>,
              },
              { key: 'name', header: 'الاسم', render: (camera) => camera.name },
              { key: 'zone', header: 'المنطقة', render: (camera) => camera.zone },
              {
                key: 'status',
                header: 'الحالة',
                render: (camera) => (
                  <Badge tone={CAMERA_STATUS_TONE[camera.status]}>
                    {CAMERA_STATUS_LABELS[camera.status]}
                  </Badge>
                ),
              },
            ]}
            empty={<StateCard bare title="لا توجد كاميرات في هذه المنشأة" />}
          />
        </div>
      )}
    </Panel>
  )
}
