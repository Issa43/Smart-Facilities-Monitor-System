import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import type { Priority } from '@/types'
import { PRIORITY_LABELS } from '@/types'
import { formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { createMaterialRequest, listMaterials, listProjects } from '@/api/construction'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button/Button'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Panel } from '@/components/ui/Panel/Panel'
import { Alert } from '@/components/ui/Feedback/Feedback'
import { Section } from '@/components/ui/Display/Display'

const schema = z.object({
  projectId: z.string().min(1, 'اختر المشروع'),
  materialName: z.string().trim().min(2, 'أدخل اسم المادة'),
  requestedQty: z.coerce.number().positive('الكمية يجب أن تكون أكبر من صفر'),
  unit: z.string().trim().min(1, 'أدخل وحدة القياس'),
  reason: z.string().trim().min(10, 'اذكر سبب الطلب في 10 أحرف على الأقل'),
  priority: z.string().min(1, 'اختر الأولوية'),
})

type RequestFormValues = z.input<typeof schema>

export function CreateMaterialRequestPage() {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [searchParams] = useSearchParams()

  const projectsQuery = useQuery({
    queryKey: qk.projects.list(user.id),
    queryFn: () => listProjects(user.id),
  })
  const materialsQuery = useQuery({
    queryKey: qk.materials.byProject(),
    queryFn: () => listMaterials(),
  })

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<RequestFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      projectId: searchParams.get('project') ?? '',
      materialName: searchParams.get('material') ?? '',
      requestedQty: 0,
      unit: '',
      reason: '',
      priority: 'medium',
    },
  })

  const selectedProject = watch('projectId')
  const lowStock =
    materialsQuery.data?.filter(
      (material) =>
        material.projectId === selectedProject &&
        material.remainingQty < material.minStockThreshold,
    ) ?? []

  const create = useMutation({
    mutationFn: (values: RequestFormValues) =>
      createMaterialRequest({
        projectId: values.projectId,
        materialName: values.materialName,
        requestedQty: Number(values.requestedQty),
        unit: values.unit,
        reason: values.reason,
        priority: values.priority as Priority,
        requestedById: user.id,
      }),
    onSuccess: (request) => {
      queryClient.invalidateQueries({ queryKey: qk.materials.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.construction(user.id) })
      showToast({
        tone: 'success',
        title: 'تم إنشاء طلب التوريد',
        description: `${request.materialName} — الحالة: قيد المعالجة`,
      })
      navigate('/construction/material-requests')
    },
  })

  return (
    <>
      <PageHeader
        title="طلب توريد مواد"
        description="يُسجَّل الطلب بحالة «قيد المعالجة» ويبقى مفتوحاً حتى اعتماده وتوريده."
        crumbs={[{ label: 'طلب جديد' }]}
      />

      {lowStock.length > 0 && (
        <Section>
          <Alert
            tone="warning"
            title="مواد تحت الحد الأدنى في هذا المشروع"
            description={lowStock
              .map(
                (material) =>
                  `${material.name}: متبقٍ ${formatNumber(material.remainingQty)} ${material.unit}`,
              )
              .join(' · ')}
          />
        </Section>
      )}

      <form onSubmit={handleSubmit((values) => create.mutate(values))} noValidate>
        <Section>
          <Panel title="تفاصيل الطلب">
            <Field label="المشروع" error={errors.projectId?.message} required>
              {(props) => (
                <select {...props} {...register('projectId')}>
                  <option value="">اختر المشروع…</option>
                  {projectsQuery.data
                    ?.filter((project) => project.status !== 'operational')
                    .map((project) => (
                      <option key={project.id} value={project.id}>
                        {project.name}
                      </option>
                    ))}
                </select>
              )}
            </Field>

            <Field
              label="اسم المادة"
              error={errors.materialName?.message}
              hint="اكتب الاسم كما هو مسجّل في قائمة المواد إن وُجد"
              required
            >
              {(props) => (
                <input
                  {...props}
                  {...register('materialName')}
                  list="known-materials"
                  placeholder="كابلات نحاسية 4×25 مم"
                />
              )}
            </Field>
            <datalist id="known-materials">
              {materialsQuery.data
                ?.filter((material) => material.projectId === selectedProject)
                .map((material) => (
                  <option key={material.id} value={material.name} />
                ))}
            </datalist>

            <FieldRow cols={3}>
              <Field label="الكمية المطلوبة" error={errors.requestedQty?.message} required>
                {(props) => (
                  <input {...props} {...register('requestedQty')} type="number" min={0} />
                )}
              </Field>
              <Field label="وحدة القياس" error={errors.unit?.message} required>
                {(props) => <input {...props} {...register('unit')} placeholder="متر طولي" />}
              </Field>
              <Field label="الأولوية" error={errors.priority?.message} required>
                {(props) => (
                  <select {...props} {...register('priority')}>
                    {Object.entries(PRIORITY_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
            </FieldRow>

            <Field
              label="سبب الطلب"
              error={errors.reason?.message}
              hint="اذكر السبب والأثر على سير العمل إن تأخر التوريد"
              required
            >
              {(props) => (
                <textarea
                  {...props}
                  {...register('reason')}
                  rows={4}
                  placeholder="مثال: انخفاض المخزون عن الحد الأدنى مع بدء تمديدات الطابق الثالث…"
                />
              )}
            </Field>
          </Panel>
        </Section>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
            إلغاء
          </Button>
          <Button type="submit" loading={create.isPending}>
            إرسال الطلب
          </Button>
        </div>
      </form>
    </>
  )
}
