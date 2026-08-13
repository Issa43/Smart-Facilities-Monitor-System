import { useRef, useState, type ReactNode } from 'react'
import { FileText, Upload, X } from 'lucide-react'
import type { Tone } from '@/types'
import { cn } from '@/lib/cn'
import styles from './Display.module.css'

/* ==========================================================================
   Timeline
   ========================================================================== */

export interface TimelineEntry {
  id: string
  title: ReactNode
  body?: ReactNode
  meta?: ReactNode
  tone?: Tone
  icon?: ReactNode
}

const TONE_CLASS: Record<Tone, string> = {
  success: styles.tlSuccess as string,
  warning: styles.tlWarning as string,
  critical: styles.tlCritical as string,
  info: styles.tlInfo as string,
  neutral: styles.tlNeutral as string,
}

export function Timeline({ entries }: { entries: TimelineEntry[] }) {
  return (
    <ol className={styles.timeline}>
      {entries.map((entry) => (
        <li key={entry.id} className={styles.tlItem}>
          <span className={cn(styles.tlDot, TONE_CLASS[entry.tone ?? 'neutral'])}>
            {entry.icon}
          </span>
          <div className={styles.tlTitle}>{entry.title}</div>
          {entry.body && <div className={styles.tlBody}>{entry.body}</div>}
          {entry.meta && <div className={styles.tlMeta}>{entry.meta}</div>}
        </li>
      ))}
    </ol>
  )
}

/* ==========================================================================
   Description list — the key/value block on every detail page
   ========================================================================== */

export interface DetailItem {
  label: string
  value: ReactNode
}

export function DescriptionList({
  items,
  single,
  className,
}: {
  items: DetailItem[]
  single?: boolean
  className?: string
}) {
  return (
    <dl className={cn(styles.dl, single && styles.dlSingle, className)}>
      {items.map((item) => (
        <div key={item.label}>
          <dt className={styles.dtLabel}>{item.label}</dt>
          <dd className={styles.ddValue}>{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}

/* ==========================================================================
   Upload zone
   ========================================================================== */

interface UploadZoneProps {
  title?: string
  hint?: string
  accept?: string
  multiple?: boolean
  onFilesChange?: (files: File[]) => void
}

/**
 * A real file picker with drag-and-drop. Files are held in local state and
 * their names listed — nothing is uploaded, because there is no backend to
 * receive them. The README lists this as a known limitation.
 */
export function UploadZone({
  title = 'اسحب الملفات هنا أو اضغط للاختيار',
  hint = 'PDF أو صور بحد أقصى 10 ميجابايت للملف',
  accept,
  multiple = true,
  onFilesChange,
}: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)

  function update(next: File[]) {
    setFiles(next)
    onFilesChange?.(next)
  }

  return (
    <div>
      <button
        type="button"
        className={cn(styles.upload, dragging && styles.uploadActive)}
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          update([...files, ...Array.from(event.dataTransfer.files)])
        }}
      >
        <span className={styles.uploadIcon}>
          <Upload size={20} strokeWidth={2} />
        </span>
        <span className={styles.uploadTitle}>{title}</span>
        <span className={styles.uploadHint}>{hint}</span>
      </button>

      {/* Visually hidden but still reachable — the button above is the visible
          trigger, and this keeps a screen reader able to pick files directly. */}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        className="sr-only"
        aria-label={title}
        onChange={(event) => update([...files, ...Array.from(event.target.files ?? [])])}
      />

      {files.length > 0 && (
        <ul className={styles.uploadFiles}>
          {files.map((file, index) => (
            <li key={`${file.name}-${index}`} className={styles.uploadFile}>
              <FileText size={14} strokeWidth={2} />
              <span className={styles.uploadFileName}>{file.name}</span>
              <button
                type="button"
                onClick={() => update(files.filter((_, i) => i !== index))}
                aria-label={`إزالة ${file.name}`}
              >
                <X size={14} strokeWidth={2.2} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/* ==========================================================================
   Avatar
   ========================================================================== */

export function Avatar({ initials, size = 36 }: { initials: string; size?: number }) {
  return (
    <span
      className={styles.avatar}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.36) }}
      aria-hidden="true"
    >
      {initials}
    </span>
  )
}

/* ==========================================================================
   Layout helpers
   ========================================================================== */

export function KpiGrid({
  children,
  cols = 4,
  className,
}: {
  children: ReactNode
  cols?: 2 | 3 | 4
  className?: string
}) {
  return (
    <div
      className={cn(
        styles.kpiGrid,
        cols === 3 && styles.kpiGrid3,
        cols === 2 && styles.kpiGrid2,
        className,
      )}
    >
      {children}
    </div>
  )
}

export function SplitGrid({
  children,
  even,
  className,
}: {
  children: ReactNode
  even?: boolean
  className?: string
}) {
  return (
    <div className={cn(styles.splitGrid, even && styles.splitGridEven, className)}>{children}</div>
  )
}

export function Section({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn(styles.section, className)}>{children}</div>
}
