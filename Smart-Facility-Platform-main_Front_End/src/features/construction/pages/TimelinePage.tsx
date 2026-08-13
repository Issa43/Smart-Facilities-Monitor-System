import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { STAGE_STATUS_LABELS, STAGE_STATUS_TONE } from '@/types'
import { formatDate, formatMonth, formatNumber } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import { listProjects, listStages } from '@/api/construction'
import { useCurrentUser } from '@/context/AuthContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Panel } from '@/components/ui/Panel/Panel'
import { ErrorState, SkeletonLines, StateCard } from '@/components/ui/Feedback/Feedback'
import { Section, Timeline } from '@/components/ui/Display/Display'
import { STATUS_COLORS } from '@/components/charts/chartTheme'
import styles from './Timeline.module.css'

const MONTHS_SHOWN = 8

/** The month columns the Gantt grid spans, starting two months back. */
function buildMonths(): { label: string; start: number; end: number }[] {
  const months: { label: string; start: number; end: number }[] = []
  const cursor = new Date()
  cursor.setDate(1)
  cursor.setHours(0, 0, 0, 0)
  cursor.setMonth(cursor.getMonth() - 2)

  for (let i = 0; i < MONTHS_SHOWN; i++) {
    const start = new Date(cursor)
    const end = new Date(cursor)
    end.setMonth(end.getMonth() + 1)
    months.push({ label: formatMonth(start), start: start.getTime(), end: end.getTime() })
    cursor.setMonth(cursor.getMonth() + 1)
  }
  return months
}

export function TimelinePage() {
  const user = useCurrentUser()
  const months = buildMonths()
  const windowStart = months[0]?.start ?? Date.now()
  const windowEnd = months[months.length - 1]?.end ?? Date.now()
  const windowSpan = windowEnd - windowStart

  const projectsQuery = useQuery({
    queryKey: qk.projects.list(user.id),
    queryFn: () => listProjects(user.id),
  })
  const stagesQuery = useQuery({ queryKey: qk.stages.all, queryFn: () => listStages() })

  const projects = projectsQuery.data?.filter((p) => p.status !== 'operational') ?? []
  const stages = stagesQuery.data ?? []

  /** Clamps a stage's date range into the visible window and returns CSS percentages. */
  function barGeometry(startDate: string, endDate: string) {
    const start = Math.max(new Date(startDate).getTime(), windowStart)
    const end = Math.min(new Date(endDate).getTime(), windowEnd)
    if (end <= windowStart || start >= windowEnd) return null

    return {
      offset: ((start - windowStart) / windowSpan) * 100,
      width: Math.max(1.5, ((end - start) / windowSpan) * 100),
    }
  }

  const todayOffset = ((Date.now() - windowStart) / windowSpan) * 100

  const upcoming = stages
    .filter((stage) => stage.status !== 'completed')
    .sort((a, b) => a.expectedEndDate.localeCompare(b.expectedEndDate))
    .slice(0, 8)

  if (stagesQuery.isError) return <ErrorState error={stagesQuery.error} />

  return (
    <>
      <PageHeader
        title="الجدول الزمني"
        description={`نظرة عامة على مراحل جميع مشاريعك عبر ${formatNumber(MONTHS_SHOWN)} أشهر. الخط العمودي يمثّل تاريخ اليوم.`}
      />

      <Section>
        <Panel title="مخطط المراحل" subtitle="امتداد كل مرحلة عبر الأشهر" flush>
          {stagesQuery.isPending ? (
            <div style={{ padding: 20 }}>
              <SkeletonLines count={7} />
            </div>
          ) : projects.length === 0 ? (
            <StateCard bare title="لا توجد مشاريع نشطة" />
          ) : (
            <div className={styles.scroll}>
              <div className={styles.chart}>
                {/* Month header. The grid is RTL, so the earliest month sits at
                    the right — matching how the rest of the app reads. */}
                <div className={styles.headRow}>
                  <div className={styles.headLabel}>المرحلة</div>
                  <div className={styles.headMonths}>
                    {months.map((month) => (
                      <div key={month.start} className={styles.headMonth}>
                        {month.label}
                      </div>
                    ))}
                    <span
                      className={styles.todayLine}
                      style={{ insetInlineStart: `${todayOffset}%` }}
                    >
                      <span className={styles.todayLabel}>اليوم</span>
                    </span>
                  </div>
                </div>

                {projects.map((project) => {
                  const projectStages = stages.filter((stage) => stage.projectId === project.id)
                  if (projectStages.length === 0) return null

                  return (
                    <div key={project.id}>
                      <div className={styles.groupRow}>
                        <Link
                          to={`/construction/projects/${project.id}`}
                          className={styles.groupName}
                        >
                          {project.name}
                        </Link>
                      </div>

                      {projectStages.map((stage) => {
                        const geometry = barGeometry(stage.startDate, stage.expectedEndDate)
                        return (
                          <div key={stage.id} className={styles.row}>
                            <Link
                              to={`/construction/stages/${stage.id}`}
                              className={styles.rowLabel}
                              title={stage.name}
                            >
                              {stage.name}
                            </Link>
                            <div className={styles.track}>
                              {months.map((month) => (
                                <span key={month.start} className={styles.cell} />
                              ))}
                              <span
                                className={styles.todayLine}
                                style={{ insetInlineStart: `${todayOffset}%` }}
                              />
                              {geometry ? (
                                <span
                                  className={styles.bar}
                                  style={
                                    {
                                      insetInlineStart: `${geometry.offset}%`,
                                      width: `${geometry.width}%`,
                                      '--bar-color': STATUS_COLORS[STAGE_STATUS_TONE[stage.status]],
                                    } as CSSProperties
                                  }
                                  title={`${stage.name} — ${stage.progressPercent}%`}
                                >
                                  <span
                                    className={styles.barFill}
                                    style={{ width: `${stage.progressPercent}%` }}
                                  />
                                </span>
                              ) : (
                                <span className={styles.outside}>خارج النطاق المعروض</span>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </Panel>
      </Section>

      <Section>
        <Panel title="المراحل القادمة" subtitle="مرتبة حسب أقرب تاريخ نهاية متوقع">
          {stagesQuery.isPending ? (
            <SkeletonLines count={5} />
          ) : upcoming.length === 0 ? (
            <StateCard bare title="جميع المراحل مكتملة" />
          ) : (
            <Timeline
              entries={upcoming.map((stage) => {
                const overdue = new Date(stage.expectedEndDate).getTime() < Date.now()
                return {
                  id: stage.id,
                  tone: overdue ? 'critical' : STAGE_STATUS_TONE[stage.status],
                  title: (
                    <Link to={`/construction/stages/${stage.id}`}>
                      {stage.name}
                      {'  '}
                      <Badge tone={STAGE_STATUS_TONE[stage.status]}>
                        {STAGE_STATUS_LABELS[stage.status]}
                      </Badge>
                    </Link>
                  ),
                  body: projects.find((p) => p.id === stage.projectId)?.name,
                  meta: `النهاية المتوقعة: ${formatDate(stage.expectedEndDate)}${overdue ? ' — متأخرة' : ''}`,
                }
              })}
            />
          )}
        </Panel>
      </Section>
    </>
  )
}
