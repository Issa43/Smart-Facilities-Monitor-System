import { useEffect, useState, type MouseEvent } from 'react'
import type { PixelPoint } from '@/types'
import { Button } from '@/components/ui/Button/Button'
import { Alert, StateCard } from '@/components/ui/Feedback/Feedback'
import { inDirection, toImagePoint, type Size } from './roiGeometry'

/**
 * Drawing on a detector's latest camera frame: an ROI polygon for the
 * intrusion model, or the two-point virtual line for ANPR. The frame comes
 * from the detector's /snapshot/raw, which has no overlays, and /info names
 * the camera it watches so a drawing is never made on the wrong camera's view.
 */
const INTRUSION_STREAM_URL =
  import.meta.env.VITE_INTRUSION_STREAM_URL?.trim() || 'http://localhost:8091/stream'

const toSvgPoints = (points: PixelPoint[]) =>
  points.map((point) => `${point.x},${point.y}`).join(' ')

type RoiDrawerProps = {
  cameraId: string
  existing: { id: string; name: string; polygon: PixelPoint[] }[]
  points: PixelPoint[]
  onChange: (points: PixelPoint[]) => void
  /** 'line' takes two points and shows which side counts as entry. */
  mode?: 'polygon' | 'line'
  /** The detector's MJPEG /stream URL; its frames are what gets drawn on. */
  streamUrl?: string
  /** Named in the messages, e.g. كاشف التسلل. */
  detectorName?: string
}

function EntryArrow({
  start,
  end,
  size,
  color,
}: {
  start: PixelPoint
  end: PixelPoint
  size: number
  color: string
}) {
  const normal = inDirection(start, end)
  const mid = { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 }
  const tip = { x: mid.x + normal.x * size * 6, y: mid.y + normal.y * size * 6 }
  // Arrow head: two short strokes back from the tip, either side of the shaft.
  const back = { x: -normal.x * size * 2, y: -normal.y * size * 2 }
  const side = { x: -normal.y * size * 1.2, y: normal.x * size * 1.2 }
  const head = [
    { x: tip.x + back.x + side.x, y: tip.y + back.y + side.y },
    tip,
    { x: tip.x + back.x - side.x, y: tip.y + back.y - side.y },
  ]
  return (
    <g stroke={color} strokeWidth={size / 2} fill="none">
      <line x1={mid.x} y1={mid.y} x2={tip.x} y2={tip.y} />
      <polyline points={toSvgPoints(head)} />
      <text
        x={tip.x + normal.x * size * 2}
        y={tip.y + normal.y * size * 2}
        fill={color}
        stroke="none"
        fontSize={size * 3}
        textAnchor="middle"
        dominantBaseline="middle"
      >
        IN
      </text>
    </g>
  )
}

export function RoiDrawer({
  cameraId,
  existing,
  points,
  onChange,
  mode = 'polygon',
  streamUrl = INTRUSION_STREAM_URL,
  detectorName = 'كاشف التسلل',
}: RoiDrawerProps) {
  const baseUrl = streamUrl.replace(/\/stream\/?$/, '')
  const isLine = mode === 'line'
  const [attempt, setAttempt] = useState(0)
  const [size, setSize] = useState<Size | null>(null)
  const [failed, setFailed] = useState(false)
  const [detectorCamera, setDetectorCamera] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(`${baseUrl}/info`)
      .then((response) => response.json() as Promise<{ camera_id?: string }>)
      .then((info) => !cancelled && setDetectorCamera(info.camera_id ?? null))
      .catch(() => !cancelled && setDetectorCamera(null))
    return () => {
      cancelled = true
    }
  }, [attempt, baseUrl])

  const reload = () => {
    setFailed(false)
    setSize(null)
    setAttempt((value) => value + 1)
  }

  const addPoint = (event: MouseEvent<SVGSVGElement>) => {
    if (!size) return
    const rect = event.currentTarget.getBoundingClientRect()
    const point = toImagePoint(event.clientX, event.clientY, rect, size)
    // A line has two points: a third click starts a new line.
    onChange(isLine && points.length >= 2 ? [point] : [...points, point])
  }

  // Scale strokes and handles with the frame, so they read the same on 720p and 4K.
  const stroke = size ? Math.max(2, Math.min(size.width, size.height) / 300) : 2
  const handle = size ? Math.max(4, Math.min(size.width, size.height) / 135) : 4

  const [lineStart, lineEnd] = points
  const needed = isLine ? 2 : 3
  const status =
    points.length < needed
      ? isLine
        ? `انقر نقطتين على الصورة لرسم الخط (${points.length} من 2)`
        : `انقر على الصورة لإضافة النقاط (${points.length} من 3 على الأقل)`
      : isLine
        ? 'الخط جاهز للحفظ — السهم يشير إلى جهة الدخول'
        : `${points.length} نقاط — جاهزة للحفظ`

  return (
    <div style={{ display: 'grid', gap: 8 }}>
      {detectorCamera && detectorCamera !== cameraId && (
        <Alert
          tone="warning"
          title="الصورة من كاميرا أخرى"
          description={`${detectorName} يراقب كاميرا غير المختارة، فلن يطابق الرسم هذه الكاميرا.`}
        />
      )}
      {failed ? (
        <StateCard
          bare
          title="تعذّر تحميل صورة الكاميرا"
          description={`شغّل ${detectorName} لهذه الكاميرا ثم أعد تحميل الصورة.`}
        />
      ) : (
        <div style={{ position: 'relative', lineHeight: 0 }}>
          <img
            key={attempt}
            src={`${baseUrl}/snapshot/raw?t=${attempt}`}
            alt="صورة الكاميرا الحالية"
            style={{ width: '100%', display: 'block', borderRadius: 8 }}
            onLoad={(event) =>
              setSize({
                width: event.currentTarget.naturalWidth,
                height: event.currentTarget.naturalHeight,
              })
            }
            onError={() => setFailed(true)}
          />
          {size && (
            <svg
              role="img"
              aria-label={
                isLine
                  ? 'ارسم الخط الافتراضي بالنقر على الصورة'
                  : 'ارسم منطقة ROI بالنقر على الصورة'
              }
              viewBox={`0 0 ${size.width} ${size.height}`}
              preserveAspectRatio="none"
              onClick={addPoint}
              style={{
                position: 'absolute',
                inset: 0,
                width: '100%',
                height: '100%',
                cursor: 'crosshair',
              }}
            >
              {existing.map((item) => {
                const [start, end] = item.polygon
                return isLine && start && end ? (
                  <g key={item.id}>
                    <polyline
                      points={toSvgPoints(item.polygon)}
                      fill="none"
                      stroke="#2563eb"
                      strokeWidth={stroke}
                      strokeDasharray={`${stroke * 4} ${stroke * 3}`}
                    />
                    <EntryArrow start={start} end={end} size={handle} color="#2563eb" />
                  </g>
                ) : (
                  <polygon
                    key={item.id}
                    points={toSvgPoints(item.polygon)}
                    fill="rgba(37, 99, 235, 0.15)"
                    stroke="#2563eb"
                    strokeWidth={stroke}
                    strokeDasharray={`${stroke * 4} ${stroke * 3}`}
                  />
                )
              })}
              {!isLine && points.length >= 3 ? (
                <polygon
                  points={toSvgPoints(points)}
                  fill="rgba(220, 38, 38, 0.2)"
                  stroke="#dc2626"
                  strokeWidth={stroke}
                />
              ) : (
                <polyline
                  points={toSvgPoints(points)}
                  fill="none"
                  stroke="#dc2626"
                  strokeWidth={stroke}
                />
              )}
              {isLine && lineStart && lineEnd && (
                <EntryArrow start={lineStart} end={lineEnd} size={handle} color="#dc2626" />
              )}
              {points.map((point, index) => (
                <circle key={index} cx={point.x} cy={point.y} r={handle} fill="#dc2626" />
              ))}
            </svg>
          )}
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <Button size="sm" variant="ghost" onClick={reload}>
          تحديث الصورة
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={!points.length}
          onClick={() => onChange(points.slice(0, -1))}
        >
          تراجع عن نقطة
        </Button>
        <Button size="sm" variant="ghost" disabled={!points.length} onClick={() => onChange([])}>
          مسح
        </Button>
        <span>{status}</span>
      </div>
    </div>
  )
}
