import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { FileText } from 'lucide-react'
import type { DocumentCategory, ProjectDocument } from '@/types'
import { DOCUMENT_CATEGORY_LABELS } from '@/types'
import { formatDate, formatFileSize, formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { createDocument, listDocuments } from '@/api/construction'
import { listUsers } from '@/api/users'
import { useCurrentUser } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { Field, FieldRow } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { ErrorState, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section, UploadZone } from '@/components/ui/Display/Display'

/** Security documentation is the policy/procedure/report subset of documents. */
const SECURITY_CATEGORIES: DocumentCategory[] = ['policy', 'procedure', 'report', 'permit']

type CategoryFilter = DocumentCategory | 'all'

const schema = z.object({
  name: z.string().trim().min(3, 'أدخل اسم الوثيقة'),
  category: z.string().min(1, 'اختر التصنيف'),
  fileType: z.string().min(1, 'اختر نوع الملف'),
})

type DocFormValues = z.infer<typeof schema>

export function SafetyDocumentationPage() {
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [uploadOpen, setUploadOpen] = useState(false)
  const [files, setFiles] = useState<File[]>([])

  const documentsQuery = useQuery({ queryKey: qk.documents.all(), queryFn: () => listDocuments() })
  const usersQuery = useQuery({ queryKey: qk.users.all, queryFn: listUsers })

  const securityDocs =
    documentsQuery.data?.filter((doc) => SECURITY_CATEGORIES.includes(doc.category)) ?? []

  const userName = useCallback(
    (id: string) => usersQuery.data?.find((u) => u.id === id)?.fullName ?? '—',
    [usersQuery.data],
  )

  const { query, setQuery, filter, setFilter, filtered } = useListFilter<
    ProjectDocument,
    CategoryFilter
  >(securityDocs, {
    searchText: useCallback((d: ProjectDocument) => d.name, []),
    matchesFilter: useCallback((d: ProjectDocument, v: CategoryFilter) => d.category === v, []),
    allValue: 'all',
  })

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<DocFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: '', category: 'policy', fileType: 'pdf' },
  })

  const upload = useMutation({
    mutationFn: (values: DocFormValues) =>
      createDocument({
        // Safety documents are platform-wide, not tied to a single project.
        projectId: null,
        name: values.name,
        category: values.category as DocumentCategory,
        fileType: values.fileType as ProjectDocument['fileType'],
        sizeKb: files[0] ? Math.round(files[0].size / 1024) : 640,
        uploadedById: user.id,
      }),
    onSuccess: (document) => {
      queryClient.invalidateQueries({ queryKey: qk.documents.all() })
      showToast({ tone: 'success', title: 'تم رفع الوثيقة', description: document.name })
      setUploadOpen(false)
      setFiles([])
      reset()
    },
  })

  const filters = [
    { value: 'all' as CategoryFilter, label: 'الكل', count: securityDocs.length },
    ...SECURITY_CATEGORIES.map((category) => ({
      value: category as CategoryFilter,
      label: DOCUMENT_CATEGORY_LABELS[category],
      count: securityDocs.filter((doc) => doc.category === category).length,
    })).filter((option) => option.count > 0),
  ]

  if (documentsQuery.isError) return <ErrorState error={documentsQuery.error} />

  return (
    <>
      <PageHeader
        title="وثائق السلامة"
        description="سياسات وإجراءات السلامة والأمن، وتقارير الحوادث الرسمية، وشهادات المطابقة."
        actions={<Button onClick={() => setUploadOpen(true)}>+ رفع وثيقة</Button>}
      />

      <Section>
        <KpiGrid cols={4}>
          <KpiCard
            label="إجمالي الوثائق"
            value={formatNumber(securityDocs.length)}
            icon="documents"
            tone="primary"
            loading={documentsQuery.isPending}
          />
          <KpiCard
            label="السياسات"
            value={formatNumber(securityDocs.filter((d) => d.category === 'policy').length)}
            icon="permissions"
            tone="info"
            loading={documentsQuery.isPending}
          />
          <KpiCard
            label="الإجراءات"
            value={formatNumber(securityDocs.filter((d) => d.category === 'procedure').length)}
            icon="response"
            tone="accent"
            loading={documentsQuery.isPending}
          />
          <KpiCard
            label="التصاريح والشهادات"
            value={formatNumber(securityDocs.filter((d) => d.category === 'permit').length)}
            icon="quality"
            tone="success"
            loading={documentsQuery.isPending}
          />
        </KpiGrid>
      </Section>

      <Toolbar>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput value={query} onChange={setQuery} placeholder="ابحث باسم الوثيقة…" />
          <FilterBar
            options={filters}
            value={filter}
            onChange={setFilter}
            label="تصفية الوثائق حسب التصنيف"
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
            header: 'الوثيقة',
            sortValue: (d) => d.name,
            render: (d) => (
              <span style={{ display: 'flex', alignItems: 'center', gap: 10, fontWeight: 700 }}>
                <FileText size={16} strokeWidth={2} />
                {d.name}
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
          { key: 'by', header: 'رفعها', render: (d) => userName(d.uploadedById) },
          {
            key: 'at',
            header: 'تاريخ الرفع',
            sortValue: (d) => d.uploadedAt,
            render: (d) => formatDate(d.uploadedAt),
          },
        ]}
        empty={
          <StateCard
            bare
            title="لا توجد وثائق مطابقة"
            description="ارفع سياسة أو إجراء سلامة جديد."
          />
        }
      />

      <Modal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        title="رفع وثيقة سلامة"
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setUploadOpen(false)}>
              إلغاء
            </Button>
            <Button loading={upload.isPending} onClick={handleSubmit((v) => upload.mutate(v))}>
              رفع الوثيقة
            </Button>
          </>
        }
      >
        <form onSubmit={handleSubmit((v) => upload.mutate(v))} noValidate>
          <Field label="اسم الوثيقة" error={errors.name?.message} required>
            {(props) => (
              <input
                {...props}
                {...register('name')}
                placeholder="سياسة الاستجابة لحالات الطوارئ"
              />
            )}
          </Field>

          <FieldRow>
            <Field label="التصنيف" error={errors.category?.message} required>
              {(props) => (
                <select {...props} {...register('category')}>
                  {SECURITY_CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {DOCUMENT_CATEGORY_LABELS[category]}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field label="نوع الملف" error={errors.fileType?.message} required>
              {(props) => (
                <select {...props} {...register('fileType')}>
                  <option value="pdf">PDF</option>
                  <option value="docx">DOCX</option>
                  <option value="xlsx">XLSX</option>
                </select>
              )}
            </Field>
          </FieldRow>

          <Field label="اختر الملف">
            {() => (
              <UploadZone onFilesChange={setFiles} multiple={false} accept=".pdf,.docx,.xlsx" />
            )}
          </Field>
        </form>
      </Modal>
    </>
  )
}
