import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import {
  FACILITY_TYPE_LABELS,
  MATERIAL_REQUEST_STATUS_LABELS,
  MATERIAL_REQUEST_STATUS_TONE,
  PROJECT_STATUS_LABELS,
  PROJECT_STATUS_TONE,
} from '@/types'
import { formatNumber, formatPercent, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { getConstructionStats } from '@/api/stats'
import { listMaterialRequests, listMaterials, listProjects, listStages } from '@/api/construction'
import { useCurrentUser } from '@/context/AuthContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Icon } from '@/components/icons'
import { Badge } from '@/components/ui/Badge/Badge'
import { LinkButton } from '@/components/ui/Button/Button'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { Panel } from '@/components/ui/Panel/Panel'
import {
  ErrorState,
  ProgressBar,
  SkeletonLines,
  StateCard,
} from '@/components/ui/Feedback/Feedback'
import { KpiGrid, Section } from '@/components/ui/Display/Display'
import { AreaChart, DonutChart } from '@/components/charts/Charts'
import { STATUS_COLORS } from '@/components/charts/chartTheme'
import shared from '@/features/shared/Dashboard.module.css'

const QUICK_ACTIONS = [
  { to: '/construction/stages', icon: 'stages', label: 'إدارة المراحل', hint: 'إضافة وتحديث' },
  {
    to: '/construction/material-requests/new',
    icon: 'materialRequests',
    label: 'طلب مواد',
    hint: 'طلب توريد جديد',
  },
  { to: '/construction/quality', icon: 'quality', label: 'فحص جودة', hint: 'تسجيل فحص' },
  { to: '/construction/daily-reports', icon: 'reports', label: 'تقرير يومي', hint: 'رفع تقرير' },
] as const

export function ConstructionDashboardPage() {
  const user = useCurrentUser()

  const statsQuery = useQuery({
    queryKey: qk.stats.construction(user.id),
    queryFn: () => getConstructionStats(user.id),
  })
  const projectsQuery = useQuery({
    queryKey: qk.projects.list(user.id),
    queryFn: () => listProjects(user.id),
  })
  const stagesQuery = useQuery({ queryKey: qk.stages.all, queryFn: () => listStages() })
  const materialsQuery = useQuery({
    queryKey: qk.materials.byProject(),
    queryFn: () => listMaterials(),
  })
  const requestsQuery = useQuery({
    queryKey: qk.materials.requests(),
    queryFn: () => listMaterialRequests(),
  })

  const stats = statsQuery.data
  const myProjects = projectsQuery.data?.filter((p) => p.status !== 'operational') ?? []
  const myProjectIds = new Set(myProjects.map((p) => p.id))

  const pendingRequests =
    requestsQuery.data?.filter((r) => r.status === 'pending' && myProjectIds.has(r.projectId)) ?? []
  const lowStock =
    materialsQuery.data?.filter(
      (m) => m.remainingQty < m.minStockThreshold && myProjectIds.has(m.projectId),
    ) ?? []
  const underReview =
    stagesQuery.data?.filter((s) => s.status === 'under_review' && myProjectIds.has(s.projectId)) ??
    []

  if (statsQuery.isError) return <ErrorState error={statsQuery.error} />

  return (
    <>
      <PageHeader
        title={
          <>
            لوحة التحكم الإنشائية
            <span className={shared.livePill}>
              <span className={shared.liveDot} />
              {formatNumber(myProjects.length)} مشروع نشط
            </span>
          </>
        }
        description="متابعة مراحل التنفيذ، نسب الإنجاز، المواد، وجودة الأعمال للمشاريع المسندة إليك."
        actions={
          <>
            <LinkButton to="/construction/progress" variant="ghost">
              متابعة التقدم
            </LinkButton>
            <LinkButton to="/construction/stages">إدارة المراحل</LinkButton>
          </>
        }
      />

      <Section>
        <KpiGrid>
          <KpiCard
            label="مشاريعي النشطة"
            value={formatNumber(stats?.myProjects ?? 0)}
            icon="projects"
            tone="primary"
            loading={statsQuery.isPending}
            footnote={`متوسط إنجاز ${formatPercent(stats?.averageProgress ?? 0)}`}
          />
          <KpiCard
            label="متوسط نسبة الإنجاز"
            value={formatPercent(stats?.averageProgress ?? 0)}
            icon="progress"
            tone="success"
            loading={statsQuery.isPending}
            progress={stats?.averageProgress ?? 0}
          />
          <KpiCard
            label="مراحل قيد التنفيذ"
            value={formatNumber(stats?.activeStages ?? 0)}
            icon="stages"
            tone="info"
            loading={statsQuery.isPending}
            footnote={`${formatNumber(stats?.stagesUnderReview ?? 0)} بانتظار الاعتماد`}
          />
          <KpiCard
            label="مراحل متأخرة"
            value={formatNumber(stats?.delayedStages ?? 0)}
            icon="corrective"
            tone={(stats?.delayedStages ?? 0) > 0 ? 'warning' : 'success'}
            loading={statsQuery.isPending}
            footnote={
              (stats?.delayedStages ?? 0) > 0 ? 'تجاوزت الموعد المخطط' : 'جميع المراحل ضمن الجدول'
            }
            footnoteTone={(stats?.delayedStages ?? 0) > 0 ? 'warning' : 'success'}
          />
          <KpiCard
            label="طلبات مواد معلّقة"
            value={formatNumber(stats?.pendingRequests ?? 0)}
            icon="materialRequests"
            tone="warning"
            loading={statsQuery.isPending}
            footnote="بانتظار المعالجة"
          />
          <KpiCard
            label="مواد تحت الحد الأدنى"
            value={formatNumber(stats?.lowStockMaterials ?? 0)}
            icon="materials"
            tone={(stats?.lowStockMaterials ?? 0) > 0 ? 'critical' : 'success'}
            loading={statsQuery.isPending}
            footnote={(stats?.lowStockMaterials ?? 0) > 0 ? 'يتطلب طلب توريد' : 'المخزون سليم'}
            footnoteTone={(stats?.lowStockMaterials ?? 0) > 0 ? 'critical' : 'success'}
          />
          <KpiCard
            label="متوسط درجة الجودة"
            value={stats?.qualityScore ? formatNumber(stats.qualityScore) : '—'}
            icon="quality"
            tone={(stats?.qualityScore ?? 0) >= 85 ? 'success' : 'warning'}
            loading={statsQuery.isPending}
            progress={stats?.qualityScore ?? 0}
          />
          <KpiCard
            label="فحوصات غير مطابقة"
            value={formatNumber(stats?.failedInspections ?? 0)}
            icon="faults"
            tone={(stats?.failedInspections ?? 0) > 0 ? 'critical' : 'success'}
            loading={statsQuery.isPending}
            footnote={
              (stats?.failedInspections ?? 0) > 0 ? 'تتطلب إعادة تنفيذ' : 'جميع الفحوصات مطابقة'
            }
            footnoteTone={(stats?.failedInspections ?? 0) > 0 ? 'critical' : 'success'}
          />
        </KpiGrid>
      </Section>

      <Section>
        <div className={shared.chartRow}>
          <Panel
            title="تقدّم التنفيذ مقابل الخطة"
            subtitle="متوسط نسبة الإنجاز عبر مشاريعك خلال آخر ستة أشهر"
          >
            {statsQuery.isPending ? (
              <SkeletonLines count={5} />
            ) : (
              <AreaChart
                data={stats?.progressTrend ?? []}
                xKey="label"
                suffix="%"
                series={[
                  { key: 'value', label: 'الإنجاز الفعلي' },
                  { key: 'planned', label: 'الإنجاز المخطط' },
                ]}
              />
            )}
          </Panel>

          <Panel title="حالة المراحل" subtitle="توزيع مراحل مشاريعك">
            {statsQuery.isPending ? (
              <SkeletonLines count={4} />
            ) : (
              <DonutChart
                slices={stats?.stagesByStatus ?? []}
                centerValue={formatNumber(
                  (stats?.stagesByStatus ?? []).reduce((sum, s) => sum + s.value, 0),
                )}
                centerLabel="مرحلة"
              />
            )}
          </Panel>
        </div>
      </Section>

      <Section>
        <div className={shared.chartRow}>
          <Panel
            title="مشاريعي"
            actions={
              <Link to="/construction/projects" className={shared.metricLabel}>
                عرض الكل <ArrowLeft size={12} style={{ display: 'inline' }} />
              </Link>
            }
          >
            {projectsQuery.isPending ? (
              <SkeletonLines count={4} />
            ) : myProjects.length === 0 ? (
              <StateCard bare title="لا توجد مشاريع مسندة إليك" />
            ) : (
              <div className={shared.strip}>
                {myProjects.map((project) => (
                  <Link
                    key={project.id}
                    to={`/construction/projects/${project.id}`}
                    className={shared.stripCard}
                  >
                    <div className={shared.stripHead}>
                      <div>
                        <span className={shared.stripName}>{project.name}</span>
                        <span className={shared.stripMeta}>
                          {FACILITY_TYPE_LABELS[project.facilityType]}
                        </span>
                      </div>
                      <Badge tone={PROJECT_STATUS_TONE[project.status]}>
                        {PROJECT_STATUS_LABELS[project.status]}
                      </Badge>
                    </div>
                    <ProgressBar value={project.progressPercent} size="sm" label={project.name} />
                    <div className={shared.stripFoot}>
                      <span>{project.currentStageName}</span>
                      <span>{formatPercent(project.progressPercent)}</span>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="إجراءات سريعة">
            <div className={shared.quickGrid}>
              {QUICK_ACTIONS.map((action) => (
                <Link key={action.to} to={action.to} className={shared.quickAction}>
                  <span className={shared.quickIcon}>
                    <Icon name={action.icon} size={18} />
                  </span>
                  <span>
                    <span className={shared.quickLabel}>{action.label}</span>
                    <span className={shared.quickHint}>{action.hint}</span>
                  </span>
                </Link>
              ))}
            </div>
          </Panel>
        </div>
      </Section>

      <Section>
        <div className={shared.chartRow}>
          <Panel title="بنود تتطلب إجراءً منك">
            {requestsQuery.isPending || stagesQuery.isPending ? (
              <SkeletonLines count={4} />
            ) : pendingRequests.length + lowStock.length + underReview.length === 0 ? (
              <StateCard
                bare
                title="لا توجد بنود معلّقة"
                description="جميع المراحل معتمدة، والمخزون ضمن الحدود، ولا توجد طلبات مواد بانتظار المعالجة."
              />
            ) : (
              <div className={shared.attentionList}>
                {underReview.map((stage) => (
                  <Link
                    key={stage.id}
                    to={`/construction/stages/${stage.id}`}
                    className={shared.attentionRow}
                  >
                    <span
                      className={shared.attentionBar}
                      style={{ background: STATUS_COLORS.warning }}
                    />
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span className={shared.attentionTitle}>{stage.name}</span>
                      <span className={shared.attentionMeta}>
                        مرحلة بانتظار الاعتماد · تحديث {formatRelative(stage.updatedAt)}
                      </span>
                    </span>
                    <Badge tone="warning">مراجعة</Badge>
                  </Link>
                ))}

                {lowStock.map((material) => (
                  <Link
                    key={material.id}
                    to="/construction/materials"
                    className={shared.attentionRow}
                  >
                    <span
                      className={shared.attentionBar}
                      style={{ background: STATUS_COLORS.critical }}
                    />
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span className={shared.attentionTitle}>{material.name}</span>
                      <span className={shared.attentionMeta}>
                        المتبقي {formatNumber(material.remainingQty)} {material.unit} — الحد الأدنى{' '}
                        {formatNumber(material.minStockThreshold)}
                      </span>
                    </span>
                    <Badge tone="critical">مخزون</Badge>
                  </Link>
                ))}

                {pendingRequests.map((request) => (
                  <Link
                    key={request.id}
                    to="/construction/material-requests"
                    className={shared.attentionRow}
                  >
                    <span
                      className={shared.attentionBar}
                      style={{ background: STATUS_COLORS.info }}
                    />
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span className={shared.attentionTitle}>{request.materialName}</span>
                      <span className={shared.attentionMeta}>
                        طلب توريد {formatNumber(request.requestedQty)} {request.unit}
                      </span>
                    </span>
                    <Badge tone={MATERIAL_REQUEST_STATUS_TONE[request.status]}>
                      {MATERIAL_REQUEST_STATUS_LABELS[request.status]}
                    </Badge>
                  </Link>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="مؤشرات سريعة">
            <div className={shared.metricList}>
              <div className={shared.metricRow}>
                <span className={shared.metricLabel}>إجمالي المراحل</span>
                <span className={shared.metricValue}>
                  {formatNumber((stats?.stagesByStatus ?? []).reduce((s, x) => s + x.value, 0))}
                </span>
              </div>
              {stats?.stagesByStatus.map((slice) => (
                <div key={slice.label} className={shared.metricRow}>
                  <span className={shared.metricLabel}>
                    <span
                      style={{
                        display: 'inline-block',
                        width: 8,
                        height: 8,
                        borderRadius: 2.5,
                        background: STATUS_COLORS[slice.tone],
                        marginInlineEnd: 7,
                      }}
                    />
                    {slice.label}
                  </span>
                  <span className={shared.metricValue}>{formatNumber(slice.value)}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </Section>
    </>
  )
}
