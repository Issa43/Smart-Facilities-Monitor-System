import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Trash2 } from 'lucide-react'
import type { SitePhoto } from '@/types'
import { formatDate, formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import {
  createSitePhoto,
  deleteSitePhoto,
  listProjects,
  listSitePhotos,
  listStages,
} from '@/api/construction'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button/Button'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { Field } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { UploadZone } from '@/components/ui/Display/Display'
import styles from '@/features/shared/ProjectDetail.module.css'

const schema = z.object({
  projectId: z.string().min(1, 'اختر المشروع'),
  stageId: z.string(),
  caption: z.string().trim().min(5, 'أدخل وصفاً للصورة'),
})

type PhotoFormValues = z.infer<typeof schema>

export function SitePhotosPage() {
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [addOpen, setAddOpen] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [pendingDelete, setPendingDelete] = useState<SitePhoto | null>(null)

  function mutationError(title: string, error: unknown) {
    showToast({
      tone: 'critical',
      title,
      description: error instanceof Error ? error.message : undefined,
    })
  }

  const projectsQuery = useQuery({
    queryKey: qk.projects.list(user.id),
    queryFn: () => listProjects(user.id),
  })
  const stagesQuery = useQuery({ queryKey: qk.stages.all, queryFn: () => listStages() })
  const photosQuery = useQuery({ queryKey: qk.sitePhotos.all(), queryFn: () => listSitePhotos() })

  const myProjectIds = new Set(projectsQuery.data?.map((p) => p.id))
  const myPhotos = photosQuery.data?.filter((p) => myProjectIds.has(p.projectId)) ?? []
  const projectName = useCallback(
    (id: string) => projectsQuery.data?.find((p) => p.id === id)?.name ?? '—',
    [projectsQuery.data],
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<SitePhoto, string>(
    myPhotos,
    {
      searchText: useCallback((photo: SitePhoto) => photo.caption, []),
      matchesFilter: useCallback(
        (photo: SitePhoto, value: string) => photo.projectId === value,
        [],
      ),
      allValue: 'all',
    },
  )

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<PhotoFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { projectId: '', stageId: '', caption: '' },
  })

  const selectedProject = watch('projectId')

  const create = useMutation({
    mutationFn: (values: PhotoFormValues) =>
      createSitePhoto({
        projectId: values.projectId,
        stageId: values.stageId || null,
        caption: values.caption,
        file: files[0] as File,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.sitePhotos.all() })
      showToast({ tone: 'success', title: 'تم رفع الصورة' })
      setAddOpen(false)
      setFiles([])
      reset()
    },
    onError: (error) => mutationError('تعذّر رفع الصورة', error),
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteSitePhoto(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.sitePhotos.all() })
      setPendingDelete(null)
      showToast({ tone: 'success', title: 'تم حذف الصورة' })
    },
    onError: (error) => mutationError('تعذّر حذف الصورة', error),
  })

  const filters = [
    { value: 'all', label: 'كل المشاريع', count: myPhotos.length },
    ...(projectsQuery.data ?? [])
      .map((project) => ({
        value: project.id,
        label: project.name,
        count: myPhotos.filter((photo) => photo.projectId === project.id).length,
      }))
      .filter((option) => option.count > 0),
  ]

  const sorted = filtered.slice().sort((a, b) => b.takenAt.localeCompare(a.takenAt))

  const dataError = [projectsQuery, stagesQuery, photosQuery].find((query) => query.isError)?.error
  if (dataError) return <ErrorState error={dataError} />

  return (
    <>
      <PageHeader
        title="صور الموقع"
        description={`${formatNumber(myPhotos.length)} صورة توثّق سير التنفيذ في مواقع مشاريعك.`}
        actions={<Button onClick={() => setAddOpen(true)}>+ رفع صور</Button>}
      />

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput value={query} onChange={setQuery} placeholder="ابحث في وصف الصور…" />
          <FilterBar
            options={filters}
            value={filter}
            onChange={setFilter}
            label="تصفية الصور حسب المشروع"
          />
        </div>
      </Toolbar>

      {projectsQuery.isPending || stagesQuery.isPending || photosQuery.isPending ? (
        <SkeletonLines count={5} />
      ) : sorted.length === 0 ? (
        <StateCard
          title="لا توجد صور"
          description="ارفع أول صورة لتوثيق حالة الموقع والأعمال المنجزة."
        />
      ) : (
        <div className={styles.photoGrid}>
          {sorted.map((photo) => (
            <figure key={photo.id} className={styles.photo}>
              <div className={styles.photoMedia} style={{ background: photo.gradient }} />
              <figcaption className={styles.photoCaption}>
                {photo.caption}
                <span className={styles.photoDate}>
                  {projectName(photo.projectId)} · {formatDate(photo.takenAt)}
                </span>
                <Button size="sm" variant="critical" onClick={() => setPendingDelete(photo)}>
                  <Trash2 size={13} /> حذف
                </Button>
              </figcaption>
            </figure>
          ))}
        </div>
      )}

      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="رفع صور الموقع"
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setAddOpen(false)}>
              إلغاء
            </Button>
            <Button loading={create.isPending} onClick={handleSubmit((v) => create.mutate(v))}>
              رفع الصور
            </Button>
          </>
        }
      >
        <form onSubmit={handleSubmit((v) => create.mutate(v))} noValidate>
          <Field label="المشروع" error={errors.projectId?.message} required>
            {(props) => (
              <select {...props} {...register('projectId')}>
                <option value="">اختر المشروع…</option>
                {projectsQuery.data
                  ?.filter((p) => p.status !== 'operational')
                  .map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
              </select>
            )}
          </Field>

          <Field label="المرحلة (اختياري)">
            {(props) => (
              <select {...props} {...register('stageId')} disabled={!selectedProject}>
                <option value="">بدون ربط بمرحلة</option>
                {stagesQuery.data
                  ?.filter((stage) => stage.projectId === selectedProject)
                  .map((stage) => (
                    <option key={stage.id} value={stage.id}>
                      {stage.name}
                    </option>
                  ))}
              </select>
            )}
          </Field>

          <Field label="وصف الصورة" error={errors.caption?.message} required>
            {(props) => (
              <input
                {...props}
                {...register('caption')}
                placeholder="تركيب لوحات التوزيع الرئيسية"
              />
            )}
          </Field>

          <Field label="الصور">
            {() => <UploadZone accept="image/*" multiple={false} onFilesChange={setFiles} />}
          </Field>
        </form>
      </Modal>

      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title="تأكيد حذف صورة الموقع"
        subtitle={pendingDelete?.caption}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setPendingDelete(null)}>
              إلغاء
            </Button>
            <Button
              variant="critical"
              loading={remove.isPending}
              onClick={() => pendingDelete && remove.mutate(pendingDelete.id)}
            >
              حذف الصورة
            </Button>
          </>
        }
      >
        سيتم حذف الصورة من سجل موقع المشروع.
      </Modal>
    </>
  )
}
