import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowLeft, Download } from 'lucide-react'
import { FACILITY_TYPE_LABELS, PROJECT_STATUS_LABELS, PROJECT_STATUS_TONE } from '@/types'
import { formatNumber, formatPercent, formatRelative } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { getAdminStats } from '@/api/stats'
import { listProjects } from '@/api/construction'
import { listIncidents } from '@/api/security'
import { listAuditLogs } from '@/api/users'
import { PageHeader } from '@/components/layout/PageHeader'
import { Icon } from '@/components/icons'
import { Badge } from '@/components/ui/Badge/Badge'
import { LinkButton } from '@/components/ui/Button/Button'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { Panel } from '@/components/ui/Panel/Panel'
import { ErrorState, ProgressBar, SkeletonLines } from '@/components/ui/Feedback/Feedback'
import { KpiGrid, Section, Timeline } from '@/components/ui/Display/Display'
import { AreaChart, DonutChart } from '@/components/charts/Charts'
import { STATUS_COLORS } from '@/components/charts/chartTheme'
import shared from '@/features/shared/Dashboard.module.css'

const QUICK_ACTIONS = [
  { to: '/admin/projects/new', icon: 'projects', label: 'إنشاء مشروع', hint: 'مشروع إنشائي جديد' },
  { to: '/admin/users', icon: 'users', label: 'إدارة المستخدمين', hint: 'إضافة أو تعديل حساب' },
  { to: '/admin/reports', icon: 'reports', label: 'إصدار تقرير', hint: 'PDF أو Excel' },
  { to: '/admin/audit-logs', icon: 'audit', label: 'سجل التدقيق', hint: 'مراجعة العمليات' },
] as const

export function AdminDashboardPage() {
  const statsQuery = useQuery({ queryKey: qk.stats.admin, queryFn: getAdminStats })
  const projectsQuery = useQuery({ queryKey: qk.projects.list(), queryFn: () => listProjects() })
  const incidentsQuery = useQuery({ queryKey: qk.incidents.list, queryFn: listIncidents })
  const auditQuery = useQuery({ queryKey: qk.auditLogs.all, queryFn: listAuditLogs })

  const stats = statsQuery.data
  const activeProjects =
    projectsQuery.data?.filter((project) => project.status !== 'operational').slice(0, 6) ?? []
  const openIncidents = incidentsQuery.data?.filter((i) => i.status !== 'closed').slice(0, 5) ?? []

  if (statsQuery.isError) return <ErrorState error={statsQuery.error} />

  return (
    <>
      <PageHeader
        title={
          <>
            مركز القيادة التنفيذي
            <span className={shared.livePill}>
              <span className={shared.liveDot} />
              بيانات حيّة
            </span>
          </>
        }
        description="نظرة شاملة على أداء المشاريع، المنشآت، الأصول، والمخاطر التشغيلية عبر المنصة بالكامل."
        actions={
          <>
            <LinkButton to="/admin/reports" variant="ghost">
              <Download size={15} strokeWidth={2} />
              تصدير تقرير
            </LinkButton>
            <LinkButton to="/admin/projects/new">+ مشروع جديد</LinkButton>
          </>
        }
      />

      <Section>
        <KpiGrid>
          <KpiCard
            label="إجمالي المشاريع"
            value={formatNumber(stats?.totalProjects ?? 0)}
            icon="projects"
            tone="primary"
            loading={statsQuery.isPending}
            footnote={`${formatNumber(stats?.activeProjects ?? 0)} مشروع نشط حالياً`}
          />
          <KpiCard
            label="نسبة الإنجاز الإجمالية"
            value={formatPercent(stats?.overallProgress ?? 0)}
            icon="progress"
            tone="success"
            loading={statsQuery.isPending}
            progress={stats?.overallProgress ?? 0}
          />
          <KpiCard
            label="صحة الأصول التشغيلية"
            value={formatPercent(stats?.assetHealth ?? 0)}
            icon="assetHealth"
            tone="accent"
            loading={statsQuery.isPending}
            progress={stats?.assetHealth ?? 0}
          />
          <KpiCard
            label="تنبيهات أمنية حرجة"
            value={formatNumber(stats?.criticalAlerts ?? 0)}
            icon="securityAlert"
            tone="critical"
            loading={statsQuery.isPending}
            footnote={
              (stats?.criticalAlerts ?? 0) > 0 ? 'يتطلب مراجعة فورية' : 'لا توجد تنبيهات حرجة'
            }
            footnoteTone={(stats?.criticalAlerts ?? 0) > 0 ? 'critical' : 'success'}
          />
          <KpiCard
            label="المنشآت التشغيلية"
            value={formatNumber(stats?.operationalFacilities ?? 0)}
            icon="facilities"
            tone="primary"
            loading={statsQuery.isPending}
            footnote={`${formatNumber(stats?.totalAssets ?? 0)} أصل مسجّل`}
          />
          <KpiCard
            label="أوامر صيانة مفتوحة"
            value={formatNumber(stats?.openWorkOrders ?? 0)}
            icon="maintenance"
            tone="warning"
            loading={statsQuery.isPending}
            footnote={`${formatNumber(stats?.overdueWorkOrders ?? 0)} متأخرة عن موعدها`}
            footnoteTone="warning"
          />
          <KpiCard
            label="حوادث مفتوحة"
            value={formatNumber(stats?.openIncidents ?? 0)}
            icon="incidents"
            tone="critical"
            loading={statsQuery.isPending}
            footnote="قيد المتابعة من مسؤول الأمن"
          />
          <KpiCard
            label="المستخدمون النشطون"
            value={formatNumber(stats?.activeUsers ?? 0)}
            icon="users"
            tone="info"
            loading={statsQuery.isPending}
            footnote={`من إجمالي ${formatNumber(stats?.totalUsers ?? 0)} حساب`}
          />
        </KpiGrid>
      </Section>

      <Section>
        <div className={shared.chartRow}>
          <Panel
            title="تقدّم التنفيذ مقابل الخطة"
            subtitle="متوسط نسبة الإنجاز عبر جميع المشاريع الإنشائية خلال آخر ستة أشهر"
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

          <Panel title="توزيع المشاريع" subtitle="حسب الحالة الحالية">
            {statsQuery.isPending ? (
              <SkeletonLines count={4} />
            ) : (
              <DonutChart
                slices={stats?.projectsByStatus ?? []}
                centerValue={formatNumber(stats?.totalProjects ?? 0)}
                centerLabel="مشروع"
              />
            )}
          </Panel>
        </div>
      </Section>

      <Section>
        <div className={shared.chartRow}>
          <Panel
            title="المشاريع النشطة"
            subtitle="المشاريع التي لم تنتقل بعد إلى مرحلة التشغيل"
            actions={
              <Link to="/admin/projects" className={shared.metricLabel}>
                عرض الكل <ArrowLeft size={12} style={{ display: 'inline' }} />
              </Link>
            }
          >
            {projectsQuery.isPending ? (
              <SkeletonLines count={5} />
            ) : (
              <div className={shared.strip}>
                {activeProjects.map((project) => (
                  <Link
                    key={project.id}
                    to={`/admin/projects/${project.id}`}
                    className={shared.stripCard}
                  >
                    <div className={shared.stripHead}>
                      <div>
                        <div className={shared.stripName}>{project.name}</div>
                        <div className={shared.stripMeta}>
                          {FACILITY_TYPE_LABELS[project.facilityType]}
                        </div>
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

            <div style={{ marginTop: 20 }}>
              <div className={shared.metricList}>
                <div className={shared.metricRow}>
                  <span className={shared.metricLabel}>حالة الأصول</span>
                  <span className={shared.metricValue}>
                    {formatPercent(stats?.assetHealth ?? 0)}
                  </span>
                </div>
                {stats?.assetsByStatus.map((slice) => (
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
            </div>
          </Panel>
        </div>
      </Section>

      <Section>
        <div className={shared.chartRow}>
          <Panel title="آخر العمليات في النظام" subtitle="سجل التدقيق — أحدث 8 عمليات">
            {auditQuery.isPending ? (
              <SkeletonLines count={6} />
            ) : (
              <Timeline
                entries={(auditQuery.data ?? []).slice(0, 8).map((entry) => ({
                  id: entry.id,
                  tone: 'info',
                  title: entry.action,
                  body: `${entry.entity} · ${entry.entityRef}`,
                  meta: formatRelative(entry.createdAt),
                }))}
              />
            )}
          </Panel>

          <Panel
            title="حوادث تتطلب متابعة"
            actions={
              <Link to="/admin/analytics" className={shared.metricLabel}>
                التحليلات <ArrowLeft size={12} style={{ display: 'inline' }} />
              </Link>
            }
          >
            {incidentsQuery.isPending ? (
              <SkeletonLines count={4} />
            ) : openIncidents.length === 0 ? (
              <p className={shared.hint}>لا توجد حوادث مفتوحة حالياً. جميع الحوادث تم إغلاقها.</p>
            ) : (
              <div className={shared.attentionList}>
                {openIncidents.map((incident) => (
                  <div key={incident.id} className={shared.attentionRow}>
                    <span
                      className={shared.attentionBar}
                      style={{
                        background:
                          STATUS_COLORS[incident.severity === 'critical' ? 'critical' : 'warning'],
                      }}
                    />
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span className={shared.attentionTitle}>{incident.reference}</span>
                      <span className={shared.attentionMeta}>{incident.location}</span>
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      </Section>
    </>
  )
}
