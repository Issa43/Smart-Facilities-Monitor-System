import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { STAGE_STATUS_LABELS, STAGE_STATUS_TONE } from '@/types'
import { formatDate, formatNumber, formatPercent } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { getConstructionStats } from '@/api/stats'
import { listProjects, listStages } from '@/api/construction'
import { useCurrentUser } from '@/context/AuthContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { KpiCard } from '@/components/ui/KpiCard/KpiCard'
import { Panel } from '@/components/ui/Panel/Panel'
import {
  ErrorState,
  ProgressBar,
  SkeletonLines,
  StateCard,
} from '@/components/ui/Feedback/Feedback'
import { KpiGrid, Section } from '@/components/ui/Display/Display'
import { AreaChart } from '@/components/charts/Charts'
import shared from '@/features/shared/Dashboard.module.css'
import styles from './Progress.module.css'

/**
 * Planned-vs-actual per stage.
 *
 * "Planned" is derived from elapsed calendar time between a stage's start and
 * expected end — that is what makes the gap meaningful: a stage 40% built but
 * 80% through its window is behind, and the bar shows it without arithmetic.
 */
function plannedPercent(startDate: string, endDate: string): number {
  const start = new Date(startDate).getTime()
  const end = new Date(endDate).getTime()
  if (end <= start) return 100
  const elapsed = ((Date.now() - start) / (end - start)) * 100
  return Math.min(100, Math.max(0, Math.round(elapsed)))
}

export function ProgressPage() {
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

  const projects = projectsQuery.data?.filter((p) => p.status !== 'operational') ?? []
  const stages = stagesQuery.data ?? []
  const stats = statsQuery.data

  if (stagesQuery.isError) return <ErrorState error={stagesQuery.error} />

  return (
    <>
      <PageHeader
        title="متابعة التقدم"
        description="مقارنة نسبة الإنجاز الفعلية بالنسبة المخططة زمنياً لكل مرحلة — الفجوة بين الشريطين تكشف التأخير مباشرة."
      />

      <Section>
        <KpiGrid cols={3}>
          <KpiCard
            label="متوسط الإنجاز"
            value={formatPercent(stats?.averageProgress ?? 0)}
            icon="progress"
            tone="primary"
            loading={statsQuery.isPending}
            progress={stats?.averageProgress ?? 0}
          />
          <KpiCard
            label="مراحل قيد التنفيذ"
            value={formatNumber(stats?.activeStages ?? 0)}
            icon="stages"
            tone="info"
            loading={statsQuery.isPending}
          />
          <KpiCard
            label="مراحل متأخرة"
            value={formatNumber(stats?.delayedStages ?? 0)}
            icon="corrective"
            tone={(stats?.delayedStages ?? 0) > 0 ? 'critical' : 'success'}
            loading={statsQuery.isPending}
            footnote={
              (stats?.delayedStages ?? 0) > 0 ? 'تجاوزت النهاية المتوقعة' : 'لا توجد تأخيرات'
            }
            footnoteTone={(stats?.delayedStages ?? 0) > 0 ? 'critical' : 'success'}
          />
        </KpiGrid>
      </Section>

      <Section>
        <Panel
          title="منحنى الإنجاز التراكمي"
          subtitle="متوسط الإنجاز الفعلي مقابل المخطط عبر مشاريعك"
        >
          {statsQuery.isPending ? (
            <SkeletonLines count={5} />
          ) : (
            <AreaChart
              data={stats?.progressTrend ?? []}
              xKey="label"
              suffix="%"
              height={260}
              series={[
                { key: 'value', label: 'الإنجاز الفعلي' },
                { key: 'planned', label: 'الإنجاز المخطط' },
              ]}
            />
          )}
        </Panel>
      </Section>

      {stagesQuery.isPending ? (
        <Panel>
          <SkeletonLines count={8} />
        </Panel>
      ) : projects.length === 0 ? (
        <StateCard
          title="لا توجد مشاريع نشطة"
          description="لم يتم إسناد أي مشروع قيد التنفيذ إليك."
        />
      ) : (
        projects.map((project) => {
          const projectStages = stages.filter((stage) => stage.projectId === project.id)
          if (projectStages.length === 0) return null

          return (
            <Section key={project.id}>
              <Panel
                title={<Link to={`/construction/projects/${project.id}`}>{project.name}</Link>}
                subtitle={`${formatNumber(projectStages.length)} مرحلة · إنجاز إجمالي ${formatPercent(project.progressPercent)}`}
                actions={
                  <Badge tone={project.progressPercent >= 70 ? 'success' : 'info'}>
                    {formatPercent(project.progressPercent)}
                  </Badge>
                }
              >
                <div className={styles.legend}>
                  <span className={styles.legendItem}>
                    <span className={styles.swatchActual} /> الإنجاز الفعلي
                  </span>
                  <span className={styles.legendItem}>
                    <span className={styles.swatchPlanned} /> المخطط زمنياً
                  </span>
                </div>

                <div className={styles.rows}>
                  {projectStages.map((stage) => {
                    const planned = plannedPercent(stage.startDate, stage.expectedEndDate)
                    const gap = stage.progressPercent - planned
                    const behind = gap < -10 && stage.status !== 'completed'

                    return (
                      <Link
                        key={stage.id}
                        to={`/construction/stages/${stage.id}`}
                        className={styles.row}
                      >
                        <div className={styles.rowHead}>
                          <span className={styles.rowName}>{stage.name}</span>
                          <span className={styles.rowMeta}>
                            {formatDate(stage.startDate)} — {formatDate(stage.expectedEndDate)}
                          </span>
                        </div>

                        <div className={styles.bars}>
                          <div className={styles.barLine}>
                            <span className={styles.barCaption}>فعلي</span>
                            <ProgressBar
                              value={stage.progressPercent}
                              size="sm"
                              label="الإنجاز الفعلي"
                            />
                            <span className={styles.barValue}>
                              {formatPercent(stage.progressPercent)}
                            </span>
                          </div>
                          <div className={styles.barLine}>
                            <span className={styles.barCaption}>مخطط</span>
                            <div className={styles.plannedTrack}>
                              <span
                                className={styles.plannedFill}
                                style={{ width: `${planned}%` }}
                              />
                            </div>
                            <span className={styles.barValue}>{formatPercent(planned)}</span>
                          </div>
                        </div>

                        <div className={styles.rowFoot}>
                          <Badge tone={STAGE_STATUS_TONE[stage.status]}>
                            {STAGE_STATUS_LABELS[stage.status]}
                          </Badge>
                          {behind ? (
                            <span className={styles.behind}>
                              متأخر بـ {formatNumber(Math.abs(gap))} نقطة عن الخطة
                            </span>
                          ) : stage.status === 'completed' ? (
                            <span className={styles.ahead}>مكتملة</span>
                          ) : (
                            <span className={shared.hint}>ضمن الخطة</span>
                          )}
                        </div>
                      </Link>
                    )
                  })}
                </div>
              </Panel>
            </Section>
          )
        })
      )}
    </>
  )
}
