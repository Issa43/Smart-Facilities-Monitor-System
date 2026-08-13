import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { FileText, Trash2 } from 'lucide-react'
import type { DocumentCategory, ProjectDocument } from '@/types'
import { DOCUMENT_CATEGORY_LABELS } from '@/types'
import { formatDate, formatFileSize, formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { createDocument, deleteDocument, listDocuments, listProjects } from '@/api/construction'
import { listUsers } from '@/api/users'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button, IconButton } from '@/components/ui/Button/Button'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { ErrorState, StateCard } from '@/components/ui/Feedback/Feedback'
import { UploadZone } from '@/components/ui/Display/Display'

type CategoryFilter = DocumentCategory | 'all'

const schema = z.object({
  projectId: z.string().min(1, 'اختر المشروع'),
  name: z.string().trim().min(3, 'أدخل اسم الملف'),
  category: z.string().min(1, 'اختر التصنيف'),
  fileType: z.string().min(1, 'اختر نوع الملف'),
})

type DocumentFormValues = z.infer<typeof schema>

export function DocumentsPage() {
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [uploadOpen, setUploadOpen] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<ProjectDocument | null>(null)
  const [files, setFiles] = useState<File[]>([])

  const projectsQuery = useQuery({
    queryKey: qk.projects.list(user.id),
    queryFn: () => listProjects(user.id),
  })
  const documentsQuery = useQuery({ queryKey: qk.documents.all(), queryFn: () => listDocuments() })
  const usersQuery = useQuery({ queryKey: qk.users.all, queryFn: listUsers })

  const myProjectIds = new Set(projectsQuery.data?.map((p) => p.id))
  const myDocuments =
    documentsQuery.data?.filter((d) => d.projectId && myProjectIds.has(d.projectId)) ?? []

  const projectName = useCallback(
    (id: string | null) => projectsQuery.data?.find((p) => p.id === id)?.name ?? '—',
    [projectsQuery.data],
  )
  const userName = useCallback(
    (id: string) => usersQuery.data?.find((u) => u.id === id)?.fullName ?? '—',
    [usersQuery.data],
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<
    ProjectDocument,
    CategoryFilter
  >(myDocuments, {
    searchText: useCallback((d: ProjectDocument) => d.name, []),
    matchesFilter: useCallback((d: ProjectDocument, v: CategoryFilter) => d.category === v, []),
    allValue: 'all',
  })

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<DocumentFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { projectId: '', name: '', category: 'drawing', fileType: 'pdf' },
  })

  const upload = useMutation({
    mutationFn: (values: DocumentFormValues) =>
      createDocument({
        projectId: values.projectId,
        name: values.name,
        category: values.category as DocumentCategory,
        fileType: values.fileType as ProjectDocument['fileType'],
        // With no backend to receive an upload, the picked file's real size is
        // the honest value to record.
        sizeKb: files[0] ? Math.round(files[0].size / 1024) : 512,
        uploadedById: user.id,
      }),
    onSuccess: (document) => {
      queryClient.invalidateQueries({ queryKey: qk.documents.all() })
      showToast({ tone: 'success', title: 'تم رفع الملف', description: document.name })
      setUploadOpen(false)
      setFiles([])
      reset()
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteDocument(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.documents.all() })
      setPendingDelete(null)
      showToast({ tone: 'success', title: 'تم حذف الملف' })
    },
  })

  const filters = [
    { value: 'all' as CategoryFilter, label: 'الكل', count: myDocuments.length },
    ...(Object.keys(DOCUMENT_CATEGORY_LABELS) as DocumentCategory[])
      .map((category) => ({
        value: category as CategoryFilter,
        label: DOCUMENT_CATEGORY_LABELS[category],
        count: myDocuments.filter((d) => d.category === category).length,
      }))
      .filter((option) => option.count > 0),
  ]

  if (documentsQuery.isError) return <ErrorState error={documentsQuery.error} />

  return (
    <>
      <PageHeader
        title="الوثائق والملفات"
        description={`${formatNumber(myDocuments.length)} ملف — مخططات، عقود، تصاريح، وتقارير فنية مرتبطة بمشاريعك.`}
        actions={<Button onClick={() => setUploadOpen(true)}>+ رفع ملف</Button>}
      />

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput value={query} onChange={setQuery} placeholder="ابحث باسم الملف…" />
          <FilterBar
            options={filters}
            value={filter}
            onChange={setFilter}
            label="تصفية الملفات حسب التصنيف"
          />
        </div>
      </Toolbar>

      <DataTable
        loading={documentsQuery.isPending}
        rows={filtered}
        rowKey={(document) => document.id}
        columns={[
          {
            key: 'name',
            header: 'الملف',
            sortValue: (d) => d.name,
            render: (d) => (
              <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <FileText size={16} strokeWidth={2} />
                <span>
                  <span style={{ display: 'block', fontWeight: 700 }}>{d.name}</span>
                  <span style={{ display: 'block', fontSize: 11.5, color: 'var(--text-muted)' }}>
                    {projectName(d.projectId)}
                  </span>
                </span>
              </span>
            ),
          },
          {
            key: 'category',
            header: 'التصنيف',
            sortValue: (d) => d.category,
            render: (d) => <Badge tone="info">{DOCUMENT_CATEGORY_LABELS[d.category]}</Badge>,
          },
          {
            key: 'type',
            header: 'النوع',
            render: (d) => <span className="mono">{d.fileType.toUpperCase()}</span>,
          },
          {
            key: 'size',
            header: 'الحجم',
            numeric: true,
            sortValue: (d) => d.sizeKb,
            render: (d) => formatFileSize(d.sizeKb),
          },
          { key: 'by', header: 'رفعه', render: (d) => userName(d.uploadedById) },
          {
            key: 'at',
            header: 'تاريخ الرفع',
            sortValue: (d) => d.uploadedAt,
            render: (d) => formatDate(d.uploadedAt),
          },
          {
            key: 'actions',
            header: '',
            width: '60px',
            render: (d) => (
              <IconButton size="sm" label={`حذف ${d.name}`} onClick={() => setPendingDelete(d)}>
                <Trash2 size={15} strokeWidth={2} />
              </IconButton>
            ),
          },
        ]}
        empty={
          <StateCard
            bare
            title="لا توجد ملفات مطابقة"
            description="ارفع ملفاً جديداً أو غيّر عوامل التصفية."
          />
        }
      />

      <Modal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        title="رفع ملف"
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setUploadOpen(false)}>
              إلغاء
            </Button>
            <Button loading={upload.isPending} onClick={handleSubmit((v) => upload.mutate(v))}>
              رفع الملف
            </Button>
          </>
        }
      >
        <form onSubmit={handleSubmit((v) => upload.mutate(v))} noValidate>
          <Field label="المشروع" error={errors.projectId?.message} required>
            {(props) => (
              <select {...props} {...register('projectId')}>
                <option value="">اختر المشروع…</option>
                {projectsQuery.data?.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            )}
          </Field>

          <Field label="اسم الملف" error={errors.name?.message} required>
            {(props) => (
              <input
                {...props}
                {...register('name')}
                placeholder="المخططات التنفيذية — الإصدار الرابع"
              />
            )}
          </Field>

          <FieldRow>
            <Field label="التصنيف" error={errors.category?.message} required>
              {(props) => (
                <select {...props} {...register('category')}>
                  {Object.entries(DOCUMENT_CATEGORY_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field label="نوع الملف" error={errors.fileType?.message} required>
              {(props) => (
                <select {...props} {...register('fileType')}>
                  <option value="pdf">PDF</option>
                  <option value="dwg">DWG</option>
                  <option value="xlsx">XLSX</option>
                  <option value="docx">DOCX</option>
                  <option value="jpg">JPG</option>
                </select>
              )}
            </Field>
          </FieldRow>

          <Field label="اختر الملف">
            {() => <UploadZone onFilesChange={setFiles} multiple={false} />}
          </Field>
        </form>
      </Modal>

      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title="تأكيد حذف الملف"
        subtitle={pendingDelete?.name}
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
              حذف الملف
            </Button>
          </>
        }
      >
        <p style={{ fontSize: 13, lineHeight: 1.9, color: 'var(--text-muted)' }}>
          سيتم حذف الملف نهائياً من سجل وثائق المشروع. لا يمكن التراجع عن هذا الإجراء.
        </p>
      </Modal>
    </>
  )
}
