import { useEffect, useState, type MouseEvent } from 'react'
import type { PixelPoint } from '@/types'
import { Button } from '@/components/ui/Button/Button'
import { Alert, StateCard } from '@/components/ui/Feedback/Feedback'
import { toImagePoint, type Size } from './roiGeometry'

/**
 * ROIs are only used by the intrusion model (fire and smoke watch the whole
 * frame), so the image to draw on is the intrusion detector's latest camera
 * frame. Its /snapshot/raw has no overlays, and /info names the camera it
 * watches so a drawing is never made on the wrong camera's view.
 */
const INTRUSION_STREAM_URL =
  import.meta.env.VITE_INTRUSION_STREAM_URL?.trim() || 'http://localhost:8091/stream'
const DETECTOR_BASE_URL = INTRUSION_STREAM_URL.replace(/\/stream\/?$/, '')

const toSvgPoints = (points: PixelPoint[]) =>
  points.map((point) => `${point.x},${point.y}`).join(' ')

type RoiDrawerProps = {
  cameraId: string
  existing: { id: string; name: string; polygon: PixelPoint[] }[]
  points: PixelPoint[]
  onChange: (points: PixelPoint[]) => void
}

export function RoiDrawer({ cameraId, existing, points, onChange }: RoiDrawerProps) {
  const [attempt, setAttempt] = useState(0)
  const [size, setSize] = useState<Size | null>(null)
  const [failed, setFailed] = useState(false)
  const [detectorCamera, setDetectorCamera] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(`${DETECTOR_BASE_URL}/info`)
      .then((response) => response.json() as Promise<{ camera_id?: string }>)
      .then((info) => !cancelled && setDetectorCamera(info.camera_id ?? null))
      .catch(() => !cancelled && setDetectorCamera(null))
    return () => {
      cancelled = true
    }
  }, [attempt])

  const reload = () => {
    setFailed(false)
    setSize(null)
    setAttempt((value) => value + 1)
  }

  const addPoint = (event: MouseEvent<SVGSVGElement>) => {
    if (!size) return
    const rect = event.currentTarget.getBoundingClientRect()
    onChange([...points, toImagePoint(event.clientX, event.clientY, rect, size)])
  }

  // Scale strokes and handles with the frame, so they read the same on 720p and 4K.
  const stroke = size ? Math.max(2, size.width / 400) : 2
  const handle = size ? Math.max(4, size.width / 180) : 4

  return (
    <div style={{ display: 'grid', gap: 8 }}>
      {detectorCamera && detectorCamera !== cameraId && (
        <Alert
          tone="warning"
          title="الصورة من كاميرا أخرى"
          description="كاشف التسلل يراقب كاميرا غير المختارة، فلن تطابق المنطقة المرسومة هذه الكاميرا."
        />
      )}
      {failed ? (
        <StateCard
          bare
          title="تعذّر تحميل صورة الكاميرا"
          description="شغّل كاشف التسلل لهذه الكاميرا ثم أعد تحميل الصورة."
        />
      ) : (
        <div style={{ position: 'relative', lineHeight: 0 }}>
          <img
            key={attempt}
            src={`${DETECTOR_BASE_URL}/snapshot/raw?t=${attempt}`}
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
              aria-label="ارسم منطقة ROI بالنقر على الصورة"
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
              {existing.map((roi) => (
                <polygon
                  key={roi.id}
                  points={toSvgPoints(roi.polygon)}
                  fill="rgba(37, 99, 235, 0.15)"
                  stroke="#2563eb"
                  strokeWidth={stroke}
                  strokeDasharray={`${stroke * 4} ${stroke * 3}`}
                />
              ))}
              {points.length >= 3 ? (
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
        <span>
          {points.length < 3
            ? `انقر على الصورة لإضافة النقاط (${points.length} من 3 على الأقل)`
            : `${points.length} نقاط — جاهزة للحفظ`}
        </span>
      </div>
    </div>
  )
}
