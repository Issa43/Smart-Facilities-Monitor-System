import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Download, FileText, Trash2 } from 'lucide-react'
import type { DocumentCategory, ProjectDocument } from '@/types'
import { DOCUMENT_CATEGORY_LABELS } from '@/types'
import { formatDate, formatFileSize, formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import {
  createSafetyDocument,
  deleteSafetyDocument,
  downloadSafetyDocument,
  listSafetyDocuments,
  listSecurityFacilities,
} from '@/api/security'
import { listUsers } from '@/api/users'
import { useToast } from '@/context/ToastContext'
import { useListFilter } from '@/hooks/useListFilter'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { FilterBar, SearchInput, Toolbar } from '@/components/ui/Controls/Controls'
import { DataTable } from '@/components/ui/DataTable/DataTable'
import { Field } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { ErrorState, StateCard } from '@/components/ui/Feedback/Feedback'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { KpiGrid, Section, UploadZone } from '@/components/ui/Display/Display'

/** Security documentation is the policy/procedure/report subset of documents. */
const SECURITY_CATEGORIES: DocumentCategory[] = ['policy', 'procedure', 'report', 'permit']

type CategoryFilter = DocumentCategory | 'all'

const schema = z.object({
  facilityId: z.string().min(1, 'اختر المنشأة'),
  name: z.string().trim().min(3, 'أدخل اسم الوثيقة'),
  category: z.string().min(1, 'اختر التصنيف'),
  file: z.custom<File>((value) => value instanceof File, 'اختر ملفاً للرفع'),
})

type DocFormValues = z.infer<typeof schema>

export function SafetyDocumentationPage() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [uploadOpen, setUploadOpen] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<ProjectDocument | null>(null)

  const documentsQuery = useQuery({ queryKey: qk.documents.all(), queryFn: listSafetyDocuments })
  const facilitiesQuery = useQuery({
    queryKey: qk.facilities.list,
    queryFn: listSecurityFacilities,
  })
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
    setValue,
    formState: { errors },
  } = useForm<DocFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { facilityId: '', name: '', category: 'policy' },
  })

  const upload = useMutation({
    mutationFn: (values: DocFormValues) =>
      createSafetyDocument({
        facilityId: values.facilityId,
        name: values.name,
        category: values.category as DocumentCategory,
        file: values.file,
      }),
    onSuccess: (document) => {
      queryClient.invalidateQueries({ queryKey: qk.documents.all() })
      showToast({ tone: 'success', title: 'تم رفع الوثيقة', description: document.name })
      setUploadOpen(false)
      reset()
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteSafetyDocument(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.documents.all() })
      setPendingDelete(null)
      showToast({ tone: 'success', title: 'تم حذف الوثيقة' })
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
          {
            key: 'actions',
            header: 'الإجراءات',
            render: (document) => (
              <div style={{ display: 'flex', gap: 8 }}>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    downloadSafetyDocument(document.id, document.originalFileName ?? document.name)
                  }
                >
                  <Download size={14} />
                  تنزيل
                </Button>
                <Button size="sm" variant="critical" onClick={() => setPendingDelete(document)}>
                  <Trash2 size={14} />
                  حذف
                </Button>
              </div>
            ),
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
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title="حذف وثيقة السلامة"
        subtitle={pendingDelete?.name}
        footer={
          <>
            <Button variant="ghost" onClick={() => setPendingDelete(null)}>
              تراجع
            </Button>
            <Button
              variant="critical"
              loading={remove.isPending}
              onClick={() => pendingDelete && remove.mutate(pendingDelete.id)}
            >
              تأكيد الحذف
            </Button>
          </>
        }
      >
        ستزال الوثيقة من قائمة وثائق السلامة النشطة.
      </Modal>

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
          <Field label="المنشأة" error={errors.facilityId?.message} required>
            {(props) => (
              <select {...props} {...register('facilityId')}>
                <option value="">اختر المنشأة…</option>
                {facilitiesQuery.data?.map((facility) => (
                  <option key={facility.id} value={facility.id}>
                    {facility.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="اسم الوثيقة" error={errors.name?.message} required>
            {(props) => (
              <input
                {...props}
                {...register('name')}
                placeholder="سياسة الاستجابة لحالات الطوارئ"
              />
            )}
          </Field>

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

          <Field label="اختر الملف" error={errors.file?.message} required>
            {() => (
              <UploadZone
                onFilesChange={(files) => {
                  if (files[0])
                    setValue('file', files[0], { shouldDirty: true, shouldValidate: true })
                }}
                multiple={false}
                accept=".pdf,.docx,.xlsx"
              />
            )}
          </Field>
        </form>
      </Modal>
    </>
  )
}
