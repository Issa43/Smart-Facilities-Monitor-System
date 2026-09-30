import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { SEVERITY_LABELS, type Severity } from '@/types'
import {
  reportCameraMaintenance,
  type CameraMaintenanceReport,
  type SecurityCamera,
} from '@/api/security'
import { useToast } from '@/context/ToastContext'
import { Button } from '@/components/ui/Button/Button'
import { Alert } from '@/components/ui/Feedback/Feedback'
import { Field } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'

const SEVERITIES = Object.keys(SEVERITY_LABELS) as Severity[]

interface CameraMaintenanceReportModalProps {
  camera: SecurityCamera | null
  onClose: () => void
}

/**
 * The Security Officer's only maintenance action: reporting the camera to
 * Operations. Investigation, work orders and closure stay with the Operations
 * Manager, so none of those controls appear here.
 */
export function CameraMaintenanceReportModal({
  camera,
  onClose,
}: CameraMaintenanceReportModalProps) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [description, setDescription] = useState('')
  const [severity, setSeverity] = useState<Severity>('medium')
  const [result, setResult] = useState<CameraMaintenanceReport | null>(null)

  const close = () => {
    setDescription('')
    setSeverity('medium')
    setResult(null)
    report.reset()
    onClose()
  }

  const report = useMutation({
    mutationFn: () =>
      reportCameraMaintenance(camera?.id ?? '', { description: description.trim(), severity }),
    onSuccess: (created) => {
      setResult(created)
      queryClient.invalidateQueries({ queryKey: ['security', 'cameras'] })
      showToast({
        tone: 'success',
        title: created.created ? 'تم إبلاغ مدير التشغيل' : 'يوجد بلاغ مفتوح لهذه الكاميرا',
        description: created.reference,
      })
    },
  })

  return (
    <Modal
      open={camera !== null}
      onClose={close}
      title="الإبلاغ عن حاجة الكاميرا للصيانة"
      subtitle={camera ? `${camera.code} — ${camera.name}` : undefined}
      footer={
        result ? (
          <Button onClick={close}>إغلاق</Button>
        ) : (
          <>
            <Button variant="ghost" onClick={close}>
              إلغاء
            </Button>
            <Button
              loading={report.isPending}
              disabled={description.trim().length === 0}
              onClick={() => report.mutate()}
            >
              إرسال البلاغ
            </Button>
          </>
        )
      }
    >
      {result ? (
        <Alert
          tone="success"
          title={
            result.created
              ? `أُنشئ البلاغ ${result.reference}`
              : `البلاغ ${result.reference} مفتوح مسبقاً لهذه الكاميرا`
          }
          description="سيتابع مدير التشغيل البلاغ ضمن مسار الأعطال وأوامر الصيانة."
        />
      ) : (
        <>
          {report.isError && (
            <Alert
              tone="critical"
              title="تعذّر إرسال البلاغ"
              description={report.error instanceof Error ? report.error.message : undefined}
            />
          )}
          <Field label="وصف المشكلة" required>
            {(props) => (
              <textarea
                {...props}
                rows={4}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            )}
          </Field>
          <Field label="الخطورة">
            {(props) => (
              <select
                {...props}
                value={severity}
                onChange={(event) => setSeverity(event.target.value as Severity)}
              >
                {SEVERITIES.map((value) => (
                  <option key={value} value={value}>
                    {SEVERITY_LABELS[value]}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </>
      )}
    </Modal>
  )
}
