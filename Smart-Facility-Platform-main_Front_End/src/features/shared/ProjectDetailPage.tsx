import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { CalendarDays, FileText, ImageIcon, MapPin, Pencil, UserCog } from 'lucide-react'
import type { Role } from '@/types'
import {
  FACILITY_TYPE_LABELS,
  INSPECTION_RESULT_LABELS,
  INSPECTION_RESULT_TONE,
  MATERIAL_REQUEST_STATUS_LABELS,
  MATERIAL_REQUEST_STATUS_TONE,
  PRIORITY_LABELS,
  PRIORITY_TONE,
  PROJECT_STATUS_LABELS,
  PROJECT_STATUS_TONE,
  STAGE_STATUS_LABELS,
  STAGE_STATUS_TONE,
} from '@/types'
import {
  formatDate,
  formatDateTime,
  formatFileSize,
  formatNumber,
  formatPercent,
} from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import {
  getProject,
  listDailyReports,
  listDocuments,
  listInspections,
  listMaterialRequests,
  listMaterials,
  listSitePhotos,
  listStages,
} from '@/api/construction'
import { listUsers } from '@/api/users'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { LinkButton } from '@/components/ui/Button/Button'
import { DataTable, type Column } from '@/components/ui/DataTable/DataTable'
import { Panel } from '@/components/ui/Panel/Panel'
import { Tabs } from '@/components/ui/Tabs/Tabs'
import {
  ErrorState,
  ProgressBar,
  SkeletonLines,
  StateCard,
} from '@/components/ui/Feedback/Feedback'
import { DescriptionList, KpiGrid, Section, SplitGrid } from '@/components/ui/Display/Display'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { ProgressRing } from '@/components/charts/Charts'
import shared from './Dashboard.module.css'
import styles from './ProjectDetail.module.css'

interface ProjectDetailPageProps {
  /** Route prefix for links back into the current role's section. */
  basePath: string
  role: Role
}

/**
 * Shared by Super Admin and Construction Manager.
 *
 * The requirements draw the line clearly: the Super Admin supervises and cannot
 * edit execution data, while the Construction Manager owns it. `role` is what
 * decides which action buttons render — the content itself is identical, so
 * duplicating this page per role would only create drift.
 */
export function ProjectDetailPage({ basePath, role }: ProjectDetailPageProps) {
  const { projectId = '' } = useParams<{ projectId: string }>()
  const canManage = role === 'construction_manager'

  const projectQuery = useQuery({
    queryKey: qk.projects.detail(projectId),
    queryFn: () => getProject(projectId),
  })
  const stagesQuery = useQuery({
    queryKey: qk.stages.byProject(projectId),
    queryFn: () => listStages(projectId),
  })
  const materialsQuery = useQuery({
    queryKey: qk.materials.byProject(projectId),
    queryFn: () => listMaterials(projectId),
  })
  const requestsQuery = useQuery({
    queryKey: qk.materials.requests(projectId),
    queryFn: () => listMaterialRequests(projectId),
  })
  const inspectionsQuery = useQuery({
    queryKey: qk.quality.inspections(projectId),
    queryFn: () => listInspections(projectId),
  })
  const reportsQuery = useQuery({
    queryKey: qk.dailyReports.all(projectId),
    queryFn: () => listDailyReports(projectId),
  })
  const documentsQuery = useQuery({
    queryKey: qk.documents.all(projectId),
    queryFn: () => listDocuments(projectId),
  })
  const photosQuery = useQuery({
    queryKey: qk.sitePhotos.all(projectId),
    queryFn: () => listSitePhotos(projectId),
  })
  const usersQuery = useQuery({ queryKey: qk.users.all, queryFn: listUsers })

  const project = projectQuery.data
  const stages = stagesQuery.data ?? []
  const materials = materialsQuery.data ?? []
  const requests = requestsQuery.data ?? []
  const inspections = inspectionsQuery.data ?? []

  const managerName =
    usersQuery.data?.find((user) => user.id === project?.constructionManagerId)?.fullName ?? '—'
  const userName = (id: string) => usersQuery.data?.find((user) => user.id === id)?.fullName ?? '—'

  if (projectQuery.isError) return <ErrorState error={projectQuery.error} />
  if (projectQuery.isPending || !project) {
    return (
      <Panel>
        <SkeletonLines count={8} />
      </Panel>
    )
  }

  const lowStock = materials.filter((m) => m.remainingQty < m.minStockThreshold)
  const completedStages = stages.filter((s) => s.status === 'completed').length
  const averageQuality =
    inspections.length === 0
      ? 0
      : Math.round(inspections.reduce((sum, i) => sum + i.score, 0) / inspections.length)

  const stageColumns: Column<(typeof stages)[number]>[] = [
    {
      key: 'name',
      header: 'المرحلة',
      sortValue: (stage) => stage.name,
      render: (stage) => (
        <div>
          <div style={{ fontWeight: 700 }}>{stage.name}</div>
          <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>
            {stage.description}
          </div>
        </div>
      ),
    },
    {
      key: 'priority',
      header: 'الأولوية',
      render: (stage) => (
        <Badge tone={PRIORITY_TONE[stage.priority]}>{PRIORITY_LABELS[stage.priority]}</Badge>
      ),
    },
    {
      key: 'progress',
      header: 'الإنجاز',
      width: '180px',
      sortValue: (stage) => stage.progressPercent,
      render: (stage) => <ProgressBar value={stage.progressPercent} size="sm" showValue />,
    },
    {
      key: 'dates',
      header: 'الفترة',
      sortValue: (stage) => stage.startDate,
      render: (stage) => (
        <span style={{ fontSize: 12 }}>
          {formatDate(stage.startDate)} — {formatDate(stage.expectedEndDate)}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'الحالة',
      render: (stage) => (
        <Badge tone={STAGE_STATUS_TONE[stage.status]}>{STAGE_STATUS_LABELS[stage.status]}</Badge>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title={project.name}
        description={project.description}
        crumbs={[{ label: project.name }]}
        actions={
          canManage ? (
            <LinkButton to={`${basePath}/stages`} variant="ghost">
              إدارة المراحل
            </LinkButton>
          ) : (
            <LinkButton to={`/admin/projects/${project.id}/edit`} variant="ghost">
              <Pencil size={15} strokeWidth={2} />
              تعديل البيانات
            </LinkButton>
          )
        }
      />

      <Section>
        <div className={styles.hero}>
          <ProgressRing percent={project.progressPercent} size={132} label="نسبة الإنجاز" />
          <div className={styles.heroBody}>
            <div className={styles.heroTop}>
              <Badge tone={PROJECT_STATUS_TONE[project.status]}>
                {PROJECT_STATUS_LABELS[project.status]}
              </Badge>
              <Badge tone="neutral" plain>
                {FACILITY_TYPE_LABELS[project.facilityType]}
              </Badge>
            </div>
            <DescriptionList
              items={[
                {
                  label: 'الموقع',
                  value: (
                    <>
                      <MapPin size={13} style={{ display: 'inline', verticalAlign: '-2px' }} />{' '}
                      {project.location}
                    </>
                  ),
                },
                {
                  label: 'مدير الإنشاءات',
                  value: (
                    <>
                      <UserCog size={13} style={{ display: 'inline', verticalAlign: '-2px' }} />{' '}
                      {managerName}
                    </>
                  ),
                },
                { label: 'تاريخ البداية', value: formatDate(project.startDate) },
                { label: 'الانتهاء المتوقع', value: formatDate(project.expectedEndDate) },
                { label: 'المرحلة الحالية', value: project.currentStageName },
                { label: 'آخر تحديث', value: formatDateTime(project.updatedAt) },
              ]}
            />
          </div>
        </div>
      </Section>

      <Section>
        <KpiGrid>
          <KpiCard
            label="عدد المراحل"
            value={formatNumber(stages.length)}
            icon="stages"
            tone="primary"
            loading={stagesQuery.isPending}
            footnote={`${formatNumber(completedStages)} مرحلة مكتملة`}
          />
          <KpiCard
            label="طلبات المواد"
            value={formatNumber(requests.length)}
            icon="materialRequests"
            tone="info"
            loading={requestsQuery.isPending}
            footnote={`${formatNumber(requests.filter((r) => r.status === 'pending').length)} قيد المعالجة`}
          />
          <KpiCard
            label="متوسط درجة الجودة"
            value={averageQuality === 0 ? '—' : formatNumber(averageQuality)}
            icon="quality"
            tone={averageQuality >= 85 ? 'success' : 'warning'}
            loading={inspectionsQuery.isPending}
            footnote={`${formatNumber(inspections.length)} فحص جودة`}
          />
          <KpiCard
            label="مواد تحت الحد الأدنى"
            value={formatNumber(lowStock.length)}
            icon="materials"
            tone={lowStock.length > 0 ? 'critical' : 'success'}
            loading={materialsQuery.isPending}
            footnote={lowStock.length > 0 ? 'يتطلب طلب توريد' : 'المخزون ضمن الحدود'}
            footnoteTone={lowStock.length > 0 ? 'critical' : 'success'}
          />
        </KpiGrid>
      </Section>

      <Tabs
        tabs={[
          {
            id: 'overview',
            label: 'نظرة عامة',
            content: (
              <SplitGrid>
                <Panel title="ملخص التنفيذ">
                  <div className={shared.metricList}>
                    <div className={shared.metricRow}>
                      <span className={shared.metricLabel}>نسبة الإنجاز الكلية</span>
                      <span className={shared.metricValue}>
                        {formatPercent(project.progressPercent)}
                      </span>
                    </div>
                    <ProgressBar value={project.progressPercent} label="نسبة الإنجاز الكلية" />
                    {stages.map((stage) => (
                      <div key={stage.id}>
                        <div className={shared.metricRow} style={{ marginBottom: 6 }}>
                          <span className={shared.metricLabel}>{stage.name}</span>
                          <span className={shared.metricValue}>
                            {formatPercent(stage.progressPercent)}
                          </span>
                        </div>
                        <ProgressBar value={stage.progressPercent} size="sm" label={stage.name} />
                      </div>
                    ))}
                  </div>
                </Panel>

                <Panel title="التوثيق">
                  <div className={shared.metricList}>
                    <div className={shared.metricRow}>
                      <span className={shared.metricLabel}>
                        <FileText size={13} style={{ verticalAlign: '-2px' }} /> الوثائق المرفوعة
                      </span>
                      <span className={shared.metricValue}>
                        {formatNumber(documentsQuery.data?.length ?? 0)}
                      </span>
                    </div>
                    <div className={shared.metricRow}>
                      <span className={shared.metricLabel}>
                        <ImageIcon size={13} style={{ verticalAlign: '-2px' }} /> صور الموقع
                      </span>
                      <span className={shared.metricValue}>
                        {formatNumber(photosQuery.data?.length ?? 0)}
                      </span>
                    </div>
                    <div className={shared.metricRow}>
                      <span className={shared.metricLabel}>
                        <CalendarDays size={13} style={{ verticalAlign: '-2px' }} /> التقارير
                        اليومية
                      </span>
                      <span className={shared.metricValue}>
                        {formatNumber(reportsQuery.data?.length ?? 0)}
                      </span>
                    </div>
                    <div className={shared.metricRow}>
                      <span className={shared.metricLabel}>فحوصات الجودة</span>
                      <span className={shared.metricValue}>{formatNumber(inspections.length)}</span>
                    </div>
                  </div>
                </Panel>
              </SplitGrid>
            ),
          },
          {
            id: 'stages',
            label: 'المراحل',
            count: stages.length,
            content: (
              <DataTable
                columns={stageColumns}
                rows={stages}
                rowKey={(stage) => stage.id}
                loading={stagesQuery.isPending}
                empty={
                  <StateCard
                    bare
                    title="لا توجد مراحل بعد"
                    description="لم يقم مدير الإنشاءات بإضافة مراحل التنفيذ لهذا المشروع حتى الآن."
                  />
                }
              />
            ),
          },
          {
            id: 'materials',
            label: 'المواد',
            count: materials.length,
            content: (
              <DataTable
                loading={materialsQuery.isPending}
                rows={materials}
                rowKey={(material) => material.id}
                columns={[
                  {
                    key: 'name',
                    header: 'المادة',
                    sortValue: (m) => m.name,
                    render: (m) => m.name,
                  },
                  { key: 'unit', header: 'الوحدة', render: (m) => m.unit },
                  {
                    key: 'required',
                    header: 'المطلوبة',
                    numeric: true,
                    sortValue: (m) => m.requiredQty,
                    render: (m) => formatNumber(m.requiredQty),
                  },
                  {
                    key: 'used',
                    header: 'المستخدمة',
                    numeric: true,
                    sortValue: (m) => m.usedQty,
                    render: (m) => formatNumber(m.usedQty),
                  },
                  {
                    key: 'remaining',
                    header: 'المتبقية',
                    numeric: true,
                    sortValue: (m) => m.remainingQty,
                    render: (m) => (
                      <span
                        style={{
                          fontWeight: 700,
                          color:
                            m.remainingQty < m.minStockThreshold
                              ? 'var(--critical-dark)'
                              : 'var(--text)',
                        }}
                      >
                        {formatNumber(m.remainingQty)}
                      </span>
                    ),
                  },
                  {
                    key: 'stock',
                    header: 'حالة المخزون',
                    render: (m) =>
                      m.remainingQty < m.minStockThreshold ? (
                        <Badge tone="critical">تحت الحد الأدنى</Badge>
                      ) : (
                        <Badge tone="success">ضمن الحد</Badge>
                      ),
                  },
                ]}
                empty={<StateCard bare title="لا توجد مواد مسجّلة" />}
              />
            ),
          },
          {
            id: 'requests',
            label: 'طلبات المواد',
            count: requests.length,
            content: (
              <DataTable
                loading={requestsQuery.isPending}
                rows={requests}
                rowKey={(request) => request.id}
                columns={[
                  {
                    key: 'material',
                    header: 'المادة',
                    sortValue: (r) => r.materialName,
                    render: (r) => r.materialName,
                  },
                  {
                    key: 'qty',
                    header: 'الكمية',
                    numeric: true,
                    render: (r) => `${formatNumber(r.requestedQty)} ${r.unit}`,
                  },
                  { key: 'reason', header: 'السبب', render: (r) => r.reason },
                  {
                    key: 'priority',
                    header: 'الأولوية',
                    render: (r) => (
                      <Badge tone={PRIORITY_TONE[r.priority]}>{PRIORITY_LABELS[r.priority]}</Badge>
                    ),
                  },
                  {
                    key: 'status',
                    header: 'الحالة',
                    render: (r) => (
                      <Badge tone={MATERIAL_REQUEST_STATUS_TONE[r.status]}>
                        {MATERIAL_REQUEST_STATUS_LABELS[r.status]}
                      </Badge>
                    ),
                  },
                  {
                    key: 'date',
                    header: 'تاريخ الطلب',
                    sortValue: (r) => r.createdAt,
                    render: (r) => formatDate(r.createdAt),
                  },
                ]}
                empty={<StateCard bare title="لا توجد طلبات مواد" />}
              />
            ),
          },
          {
            id: 'quality',
            label: 'الجودة',
            count: inspections.length,
            content: (
              <DataTable
                loading={inspectionsQuery.isPending}
                rows={inspections}
                rowKey={(inspection) => inspection.id}
                columns={[
                  {
                    key: 'title',
                    header: 'الفحص',
                    sortValue: (i) => i.title,
                    render: (i) => (
                      <div>
                        <div style={{ fontWeight: 700 }}>{i.title}</div>
                        <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>
                          {i.notes}
                        </div>
                      </div>
                    ),
                  },
                  { key: 'inspector', header: 'المفتّش', render: (i) => userName(i.inspectorId) },
                  {
                    key: 'score',
                    header: 'الدرجة',
                    numeric: true,
                    sortValue: (i) => i.score,
                    render: (i) => formatNumber(i.score),
                  },
                  {
                    key: 'result',
                    header: 'النتيجة',
                    render: (i) => (
                      <Badge tone={INSPECTION_RESULT_TONE[i.result]}>
                        {INSPECTION_RESULT_LABELS[i.result]}
                      </Badge>
                    ),
                  },
                  {
                    key: 'date',
                    header: 'التاريخ',
                    sortValue: (i) => i.inspectedAt,
                    render: (i) => formatDate(i.inspectedAt),
                  },
                ]}
                empty={<StateCard bare title="لا توجد فحوصات جودة" />}
              />
            ),
          },
          {
            id: 'reports',
            label: 'التقارير اليومية',
            count: reportsQuery.data?.length ?? 0,
            content: (
              <DataTable
                loading={reportsQuery.isPending}
                rows={reportsQuery.data ?? []}
                rowKey={(report) => report.id}
                columns={[
                  {
                    key: 'title',
                    header: 'التقرير',
                    render: (r) => (
                      <div>
                        <div style={{ fontWeight: 700 }}>{r.title}</div>
                        <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>
                          {r.summary}
                        </div>
                      </div>
                    ),
                  },
                  {
                    key: 'workforce',
                    header: 'العمالة',
                    numeric: true,
                    render: (r) => formatNumber(r.workforceCount),
                  },
                  {
                    key: 'photos',
                    header: 'الصور',
                    numeric: true,
                    render: (r) => formatNumber(r.photoCount),
                  },
                  { key: 'author', header: 'أعدّه', render: (r) => userName(r.authorId) },
                  {
                    key: 'date',
                    header: 'التاريخ',
                    sortValue: (r) => r.reportDate,
                    render: (r) => formatDate(r.reportDate),
                  },
                ]}
                empty={<StateCard bare title="لا توجد تقارير يومية" />}
              />
            ),
          },
          {
            id: 'documents',
            label: 'الوثائق',
            count: documentsQuery.data?.length ?? 0,
            content: (
              <DataTable
                loading={documentsQuery.isPending}
                rows={documentsQuery.data ?? []}
                rowKey={(document) => document.id}
                columns={[
                  {
                    key: 'name',
                    header: 'الملف',
                    sortValue: (d) => d.name,
                    render: (d) => (
                      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <FileText size={15} strokeWidth={2} />
                        {d.name}
                      </span>
                    ),
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
                    header: 'التاريخ',
                    sortValue: (d) => d.uploadedAt,
                    render: (d) => formatDate(d.uploadedAt),
                  },
                ]}
                empty={<StateCard bare title="لا توجد وثائق مرفوعة" />}
              />
            ),
          },
          {
            id: 'photos',
            label: 'صور الموقع',
            count: photosQuery.data?.length ?? 0,
            content:
              (photosQuery.data?.length ?? 0) === 0 ? (
                <StateCard title="لا توجد صور" description="لم يتم رفع أي صور لهذا المشروع بعد." />
              ) : (
                <div className={styles.photoGrid}>
                  {photosQuery.data?.map((photo) => (
                    <figure key={photo.id} className={styles.photo}>
                      <div className={styles.photoMedia} style={{ background: photo.gradient }} />
                      <figcaption className={styles.photoCaption}>
                        {photo.caption}
                        <span className={styles.photoDate}>{formatDate(photo.takenAt)}</span>
                      </figcaption>
                    </figure>
                  ))}
                </div>
              ),
          },
        ]}
      />

      {!canManage && (
        <Section>
          <Panel title="صلاحية الإشراف">
            <p className={shared.hint}>
              يملك المدير العام صلاحية الاطلاع الكامل على بيانات التنفيذ دون تعديلها. تعديل المراحل
              والمواد وفحوصات الجودة من مسؤولية{' '}
              <Link
                to={`${basePath}/projects`}
                style={{ color: 'var(--primary-dark)', fontWeight: 700 }}
              >
                مدير الإنشاءات المسؤول
              </Link>
              .
            </p>
          </Panel>
        </Section>
      )}
    </>
  )
}
