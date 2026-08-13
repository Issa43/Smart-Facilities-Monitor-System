import { Skeleton } from '@/components/ui/Feedback/Feedback'

/**
 * Shown while a lazy route chunk downloads.
 *
 * Deliberately shaped like a page (header block, KPI row, panel) rather than a
 * spinner, so the layout does not jump when the real page arrives.
 */
export function RouteFallback() {
  return (
    <div
      style={{ padding: 'var(--space-6) var(--space-7)' }}
      role="status"
      aria-label="جارٍ التحميل"
    >
      <Skeleton height={13} width={180} />
      <div style={{ height: 14 }} />
      <Skeleton height={28} width={320} />
      <div style={{ height: 28 }} />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
          gap: 'var(--space-4)',
        }}
      >
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} height={104} style={{ borderRadius: 'var(--radius-lg)' }} />
        ))}
      </div>

      <div style={{ height: 24 }} />
      <Skeleton height={280} style={{ borderRadius: 'var(--radius-lg)' }} />
    </div>
  )
}
