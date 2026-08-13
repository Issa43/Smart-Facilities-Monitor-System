import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { Check, Square, SquareCheckBig, X } from 'lucide-react'
import type { WorkOrderStatus } from '@/types'
import {
  MAINTENANCE_TYPE_LABELS,
  PRIORITY_LABELS,
  PRIORITY_TONE,
  WORK_ORDER_STATUS_LABELS,
  WORK_ORDER_STATUS_TONE,
} from '@/types'
import { formatDate, formatDateTime, formatNumber, formatPercent } from '@/lib/format'
import { qk } from '@/lib/queryKeys'
import {
  getAsset,
  getWorkOrder,
  setWorkOrderStatus,
  toggleWorkOrderTask,
  updateWorkOrder,
} from '@/api/operations'
import { listUsers } from '@/api/users'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge/Badge'
import { Button } from '@/components/ui/Button/Button'
import { Field } from '@/components/ui/Field/Field'
import { Modal } from '@/components/ui/Modal/Modal'
import { Panel } from '@/components/ui/Panel/Panel'
import { Alert, ErrorState, ProgressBar, SkeletonLines } from '@/components/ui/Feedback/Feedback'
import { DescriptionList, Section, SplitGrid } from '@/components/ui/Display/Display'
import shared from '@/features/shared/Dashboard.module.css'
import styles from './WorkOrder.module.css'

export function WorkOrderDetailPage() {
  const { orderId = '' } = useParams<{ orderId: string }>()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [closeOpen, setCloseOpen] = useState(false)
  const [notes, setNotes] = useState('')

  const orderQuery = useQuery({
    queryKey: qk.workOrders.detail(orderId),
    queryFn: () => getWorkOrder(orderId),
  })
  const order = orderQuery.data

  const assetQuery = useQuery({
    queryKey: qk.assets.detail(order?.assetId ?? ''),
    queryFn: () => getAsset(order?.assetId as string),
    enabled: Boolean(order?.assetId),
  })
  const usersQuery = useQuery({ queryKey: qk.users.all, queryFn: listUsers })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: qk.workOrders.all })
    queryClient.invalidateQueries({ queryKey: qk.assets.all })
    queryClient.invalidateQueries({ queryKey: qk.stats.operations })
  }

  const toggleTask = useMutation({
    mutationFn: (taskId: string) => toggleWorkOrderTask(orderId, taskId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.workOrders.all }),
  })

  const changeStatus = useMutation({
    mutationFn: (status: WorkOrderStatus) => setWorkOrderStatus(orderId, status),
    onSuccess: (updated) => {
      invalidate()
      setCloseOpen(false)
      showToast({
        tone: updated.status === 'completed' ? 'success' : 'info',
        title: `تم تحديث الأمر إلى «${WORK_ORDER_STATUS_LABELS[updated.status]}»`,
        description:
          updated.status === 'completed'
            ? 'تم تحديث تاريخ آخر صيانة ودرجة صحة الأصل تلقائياً.'
            : undefined,
      })
    },
  })

  const saveNotes = useMutation({
    mutationFn: () => updateWorkOrder(orderId, { notes }),
    onSuccess: () => {
      invalidate()
      showToast({ tone: 'success', title: 'تم حفظ الملاحظات' })
    },
  })

  if (orderQuery.isError) return <ErrorState error={orderQuery.error} />
  if (orderQuery.isPending || !order) {
    return (
      <Panel>
        <SkeletonLines count={7} />
      </Panel>
    )
  }

  const doneTasks = order.tasks.filter((task) => task.done).length
  const taskProgress =
    order.tasks.length === 0 ? 0 : Math.round((doneTasks / order.tasks.length) * 100)
  const allTasksDone = order.tasks.length > 0 && doneTasks === order.tasks.length
  const isClosed = order.status === 'completed' || order.status === 'cancelled'
  const overdue = !isClosed && new Date(order.scheduledDate).getTime() < Date.now()

  const userName = (id: string | null) =>
    id ? (usersQuery.data?.find((u) => u.id === id)?.fullName ?? '—') : 'غير مُسند'

  return (
    <>
      <PageHeader
        title={order.reason}
        description={order.description}
        crumbs={[{ label: order.reference }]}
        actions={
          !isClosed && (
            <>
              {order.status === 'open' && (
                <Button variant="ghost" onClick={() => changeStatus.mutate('in_progress')}>
                  بدء التنفيذ
                </Button>
              )}
              <Button variant="critical" onClick={() => changeStatus.mutate('cancelled')}>
                <X size={15} strokeWidth={2.2} />
                إلغاء الأمر
              </Button>
              <Button variant="success" onClick={() => setCloseOpen(true)}>
                <Check size={15} strokeWidth={2.2} />
                إغلاق الأمر
              </Button>
            </>
          )
        }
      />

      {overdue && (
        <Section>
          <Alert
            tone="warning"
            title="أمر صيانة متأخر"
            description={`تجاوز الأمر تاريخ التنفيذ المجدول (${formatDate(order.scheduledDate)}) ولم يُغلق بعد.`}
          />
        </Section>
      )}

      <Section>
        <Panel>
          <div className={styles.headerRow}>
            <div>
              <span className={styles.reference}>{order.reference}</span>
              <div className={styles.badges}>
                <Badge tone={WORK_ORDER_STATUS_TONE[order.status]}>
                  {WORK_ORDER_STATUS_LABELS[order.status]}
                </Badge>
                <Badge tone={PRIORITY_TONE[order.priority]}>
                  أولوية {PRIORITY_LABELS[order.priority]}
                </Badge>
                <Badge tone={order.maintenanceType === 'preventive' ? 'info' : 'warning'}>
                  {MAINTENANCE_TYPE_LABELS[order.maintenanceType]}
                </Badge>
              </div>
            </div>
          </div>

          <DescriptionList
            items={[
              {
                label: 'الأصل',
                value: assetQuery.data ? (
                  <Link
                    to={`/operations/assets/${assetQuery.data.id}`}
                    style={{ color: 'var(--primary-dark)', fontWeight: 700 }}
                  >
                    {assetQuery.data.name}
                  </Link>
                ) : (
                  '—'
                ),
              },
              { label: 'موعد التنفيذ', value: formatDate(order.scheduledDate) },
              { label: 'المُسند إليه', value: userName(order.assignedToId) },
              { label: 'تاريخ الإنشاء', value: formatDateTime(order.createdAt) },
              {
                label: 'تاريخ الإغلاق',
                value: order.completedDate ? formatDateTime(order.completedDate) : 'لم يُغلق بعد',
              },
              {
                label: 'نسبة إنجاز البنود',
                value: `${formatNumber(doneTasks)} من ${formatNumber(order.tasks.length)}`,
              },
            ]}
          />
        </Panel>
      </Section>

      <SplitGrid>
        <Panel
          title="قائمة بنود التنفيذ"
          subtitle="اضغط على أي بند لتعليمه كمنجز"
          actions={
            <Badge tone={allTasksDone ? 'success' : 'info'}>{formatPercent(taskProgress)}</Badge>
          }
        >
          {order.tasks.length === 0 ? (
            <p className={shared.hint}>لا توجد بنود تنفيذ مسجّلة لهذا الأمر.</p>
          ) : (
            <>
              <div style={{ marginBottom: 16 }}>
                <ProgressBar value={taskProgress} label="نسبة إنجاز البنود" />
              </div>
              <ul className={styles.tasks}>
                {order.tasks.map((task) => (
                  <li key={task.id}>
                    <button
                      type="button"
                      className={task.done ? styles.taskDone : styles.task}
                      onClick={() => toggleTask.mutate(task.id)}
                      disabled={isClosed || toggleTask.isPending}
                      aria-pressed={task.done}
                    >
                      {task.done ? (
                        <SquareCheckBig size={17} strokeWidth={2.2} />
                      ) : (
                        <Square size={17} strokeWidth={2} />
                      )}
                      <span>{task.label}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Panel>

        <Panel title="ملاحظات التنفيذ">
          <Field label="ملاحظات فنية" hint="تُحفظ مع أمر الصيانة">
            {(props) => (
              <textarea
                {...props}
                rows={6}
                defaultValue={order.notes}
                onChange={(event) => setNotes(event.target.value)}
                disabled={isClosed}
                placeholder="تفاصيل ما تم تنفيذه، القطع المستبدلة، والملاحظات على حالة الأصل…"
              />
            )}
          </Field>
          {!isClosed && (
            <Button
              variant="ghost"
              block
              loading={saveNotes.isPending}
              disabled={notes.length === 0}
              onClick={() => saveNotes.mutate()}
            >
              حفظ الملاحظات
            </Button>
          )}
        </Panel>
      </SplitGrid>

      <Modal
        open={closeOpen}
        onClose={() => setCloseOpen(false)}
        title="إغلاق أمر الصيانة"
        subtitle={order.reference}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setCloseOpen(false)}>
              إلغاء
            </Button>
            <Button
              variant="success"
              loading={changeStatus.isPending}
              onClick={() => changeStatus.mutate('completed')}
            >
              تأكيد الإغلاق
            </Button>
          </>
        }
      >
        {!allTasksDone && order.tasks.length > 0 && (
          <Alert
            tone="warning"
            title="بنود غير مكتملة"
            description={`${formatNumber(order.tasks.length - doneTasks)} بند لم يُعلَّم كمنجز بعد. يمكنك الإغلاق على أي حال، لكن يُفضّل استكمالها أولاً.`}
          />
        )}
        <p style={{ fontSize: 13, lineHeight: 1.9, color: 'var(--text-muted)', marginTop: 14 }}>
          عند الإغلاق سيسجّل النظام تاريخ الإنجاز، ويحدّث تاريخ آخر صيانة للأصل، ويرفع درجة صحته.
        </p>
      </Modal>
    </>
  )
}
