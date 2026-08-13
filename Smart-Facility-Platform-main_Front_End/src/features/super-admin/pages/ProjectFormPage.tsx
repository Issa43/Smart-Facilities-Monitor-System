import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Trash2 } from 'lucide-react'
import { FACILITY_TYPE_LABELS, PROJECT_STATUS_LABELS } from '@/types'
import type { FacilityType, ProjectStatus } from '@/types'
import { qk } from '@/lib/queryKeys'
import { createProject, deleteProject, getProject, updateProject } from '@/api/construction'
import { listUsers } from '@/api/users'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button/Button'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Panel } from '@/components/ui/Panel/Panel'
import { Modal } from '@/components/ui/Modal/Modal'
import { Alert, ErrorState, SkeletonLines } from '@/components/ui/Feedback/Feedback'
import { Section, UploadZone } from '@/components/ui/Display/Display'

const schema = z
  .object({
    name: z.string().trim().min(3, 'اسم المشروع يجب ألا يقل عن 3 أحرف'),
    facilityType: z.string().min(1, 'اختر نوع المنشأة'),
    description: z.string().trim().min(10, 'أدخل وصفاً لا يقل عن 10 أحرف'),
    location: z.string().trim().min(3, 'أدخل موقع المشروع'),
    startDate: z.string().min(1, 'اختر تاريخ البداية'),
    expectedEndDate: z.string().min(1, 'اختر تاريخ الانتهاء المتوقع'),
    status: z.string().min(1, 'اختر حالة المشروع'),
    constructionManagerId: z.string().min(1, 'اختر مدير الإنشاءات المسؤول'),
  })
  .refine((values) => new Date(values.expectedEndDate) > new Date(values.startDate), {
    message: 'تاريخ الانتهاء المتوقع يجب أن يكون بعد تاريخ البداية',
    path: ['expectedEndDate'],
  })

type ProjectFormValues = z.infer<typeof schema>

/** Serves both /admin/projects/new and /admin/projects/:id/edit. */
export function ProjectFormPage({ mode }: { mode: 'create' | 'edit' }) {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [confirmDelete, setConfirmDelete] = useState(false)

  const isEdit = mode === 'edit'

  const projectQuery = useQuery({
    queryKey: qk.projects.detail(projectId ?? ''),
    queryFn: () => getProject(projectId as string),
    enabled: isEdit && Boolean(projectId),
  })

  const usersQuery = useQuery({ queryKey: qk.users.all, queryFn: listUsers })
  const managers = usersQuery.data?.filter((user) => user.role === 'construction_manager') ?? []

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ProjectFormValues>({
    resolver: zodResolver(schema),
    // `values` (not defaultValues) so the form re-syncs once the query resolves.
    values: projectQuery.data
      ? {
          name: projectQuery.data.name,
          facilityType: projectQuery.data.facilityType,
          description: projectQuery.data.description,
          location: projectQuery.data.location,
          startDate: projectQuery.data.startDate.slice(0, 10),
          expectedEndDate: projectQuery.data.expectedEndDate.slice(0, 10),
          status: projectQuery.data.status,
          constructionManagerId: projectQuery.data.constructionManagerId,
        }
      : undefined,
    defaultValues: {
      name: '',
      facilityType: '',
      description: '',
      location: '',
      startDate: '',
      expectedEndDate: '',
      status: 'planning',
      constructionManagerId: '',
    },
  })

  const save = useMutation({
    mutationFn: (values: ProjectFormValues) => {
      const payload = {
        ...values,
        facilityType: values.facilityType as FacilityType,
        status: values.status as ProjectStatus,
        startDate: new Date(values.startDate).toISOString(),
        expectedEndDate: new Date(values.expectedEndDate).toISOString(),
      }
      return isEdit ? updateProject(projectId as string, payload) : createProject(payload)
    },
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: qk.projects.all })
      queryClient.invalidateQueries({ queryKey: qk.stats.admin })
      showToast({
        tone: 'success',
        title: isEdit ? 'تم حفظ التعديلات' : 'تم إنشاء المشروع',
        description: project.name,
      })
      navigate(`/admin/projects/${project.id}`)
    },
    onError: (error) =>
      showToast({
        tone: 'critical',
        title: 'تعذّر الحفظ',
        description: error instanceof Error ? error.message : undefined,
      }),
  })

  const remove = useMutation({
    mutationFn: () => deleteProject(projectId as string),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.projects.all })
      showToast({ tone: 'success', title: 'تم حذف المشروع' })
      navigate('/admin/projects')
    },
  })

  if (isEdit && projectQuery.isError) return <ErrorState error={projectQuery.error} />

  return (
    <>
      <PageHeader
        title={isEdit ? 'تعديل بيانات المشروع' : 'إنشاء مشروع جديد'}
        description={
          isEdit
            ? 'حدّث البيانات الأساسية للمشروع. لا يؤثر ذلك على مراحل التنفيذ المسجّلة.'
            : 'أدخل البيانات الأساسية للمشروع. بعد الحفظ سيظهر تلقائياً في لوحة تحكم مدير الإنشاءات المسؤول.'
        }
        crumbs={[{ label: isEdit ? 'تعديل' : 'مشروع جديد' }]}
      />

      {isEdit && projectQuery.isPending ? (
        <Panel>
          <SkeletonLines count={8} />
        </Panel>
      ) : (
        <form onSubmit={handleSubmit((values) => save.mutate(values))} noValidate>
          <Section>
            <Panel title="البيانات الأساسية">
              <Field label="اسم المشروع" error={errors.name?.message} required>
                {(props) => (
                  <input
                    {...props}
                    {...register('name')}
                    placeholder="مثال: مستشفى الملك فهد التخصصي"
                  />
                )}
              </Field>

              <FieldRow>
                <Field label="نوع المنشأة" error={errors.facilityType?.message} required>
                  {(props) => (
                    <select {...props} {...register('facilityType')}>
                      <option value="">اختر النوع…</option>
                      {Object.entries(FACILITY_TYPE_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>

                <Field label="موقع المشروع" error={errors.location?.message} required>
                  {(props) => (
                    <input {...props} {...register('location')} placeholder="المدينة — الحي" />
                  )}
                </Field>
              </FieldRow>

              <Field
                label="وصف المشروع"
                error={errors.description?.message}
                hint="نطاق العمل، عدد المباني، والطاقة الاستيعابية"
                required
              >
                {(props) => <textarea {...props} {...register('description')} rows={4} />}
              </Field>
            </Panel>
          </Section>

          <Section>
            <Panel title="الجدول الزمني والإسناد">
              <FieldRow>
                <Field label="تاريخ البداية" error={errors.startDate?.message} required>
                  {(props) => <input {...props} {...register('startDate')} type="date" />}
                </Field>
                <Field
                  label="تاريخ الانتهاء المتوقع"
                  error={errors.expectedEndDate?.message}
                  required
                >
                  {(props) => <input {...props} {...register('expectedEndDate')} type="date" />}
                </Field>
              </FieldRow>

              <FieldRow>
                <Field label="حالة المشروع" error={errors.status?.message} required>
                  {(props) => (
                    <select {...props} {...register('status')}>
                      {Object.entries(PROJECT_STATUS_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>

                <Field
                  label="مدير الإنشاءات المسؤول"
                  error={errors.constructionManagerId?.message}
                  hint="سيظهر المشروع في لوحة تحكمه فور الحفظ"
                  required
                >
                  {(props) => (
                    <select {...props} {...register('constructionManagerId')}>
                      <option value="">اختر المدير…</option>
                      {managers.map((manager) => (
                        <option key={manager.id} value={manager.id}>
                          {manager.fullName}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
              </FieldRow>
            </Panel>
          </Section>

          <Section>
            <Panel title="صورة المشروع" subtitle="اختيارية — تُعرض في بطاقة المشروع">
              <UploadZone
                accept="image/*"
                multiple={false}
                title="اسحب صورة المشروع هنا أو اضغط للاختيار"
                hint="JPG أو PNG بحد أقصى 5 ميجابايت"
              />
            </Panel>
          </Section>

          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
              إلغاء
            </Button>
            <Button type="submit" loading={isSubmitting || save.isPending}>
              {isEdit ? 'حفظ التعديلات' : 'إنشاء المشروع'}
            </Button>
          </div>
        </form>
      )}

      {isEdit && (
        <Section>
          <Panel
            title="منطقة الخطر"
            subtitle="حذف المشروع يزيل جميع مراحله وموادّه وطلباته نهائياً — لا يمكن التراجع."
            className="danger-zone"
            actions={
              <Button variant="critical" onClick={() => setConfirmDelete(true)}>
                <Trash2 size={15} strokeWidth={2} />
                حذف المشروع
              </Button>
            }
          >
            <Alert
              tone="warning"
              title="قبل الحذف"
              description="إذا كان المشروع قد بدأ التنفيذ فعلياً، يُنصح بتغيير حالته إلى «متوقف مؤقتاً» بدلاً من حذفه، للحفاظ على السجل التاريخي."
            />
          </Panel>
        </Section>
      )}

      <Modal
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="تأكيد حذف المشروع"
        subtitle={projectQuery.data?.name}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
              إلغاء
            </Button>
            <Button variant="critical" loading={remove.isPending} onClick={() => remove.mutate()}>
              نعم، احذف المشروع
            </Button>
          </>
        }
      >
        <p style={{ fontSize: 13, lineHeight: 1.9, color: 'var(--text-muted)' }}>
          سيتم حذف المشروع وجميع المراحل والمواد وطلبات المواد المرتبطة به بشكل نهائي. لا يمكن
          التراجع عن هذا الإجراء.
        </p>
      </Modal>
    </>
  )
}
