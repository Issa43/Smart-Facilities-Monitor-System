import { useEffect, useId, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import styles from './LocationPicker.module.css'

/** Shown only until the user picks a point. Never saved: a project with no
 *  chosen location keeps null coordinates rather than inheriting this. */
const PREVIEW_CENTRE: [number, number] = [34.8021, 38.9968] // Syria, country view
const PREVIEW_ZOOM = 6
const PICKED_ZOOM = 15

const OSM_TILES = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'

export interface LatLng {
  latitude: number
  longitude: number
}

interface Props {
  value: LatLng | null
  onChange: (value: LatLng) => void
  /** Rendered above the map; the caller owns the wording. */
  label?: string
  hint?: string
  disabled?: boolean
}

/**
 * Pick a project's exact point on an OpenStreetMap map.
 *
 * Deliberately plain Leaflet rather than a React wrapper: the map is imperative
 * by nature and this keeps the dependency surface to one package. Leaflet owns
 * the DOM inside its container, so React never re-renders through it — the
 * effect below only syncs the marker when the value changes from outside.
 *
 * There is no geocoding: a textual location is never turned into coordinates,
 * and coordinates are only ever produced by the user clicking a point.
 */
export function LocationPicker({ value, onChange, label, hint, disabled = false }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markerRef = useRef<L.Marker | null>(null)
  // Kept in a ref so the click handler is installed once and never goes stale.
  const onChangeRef = useRef(onChange)
  const headingId = useId()
  onChangeRef.current = onChange

  useEffect(() => {
    const container = containerRef.current
    if (!container || mapRef.current) return

    // Leaflet's default marker icons resolve to bundler-relative URLs that Vite
    // cannot rewrite; a divIcon avoids the broken-image problem entirely.
    const icon = L.divIcon({
      className: styles.pin,
      html: '<span aria-hidden="true"></span>',
      iconSize: [22, 22],
      iconAnchor: [11, 22],
    })

    const map = L.map(container, { attributionControl: true }).setView(
      PREVIEW_CENTRE,
      PREVIEW_ZOOM,
    )
    L.tileLayer(OSM_TILES, { attribution: OSM_ATTRIBUTION, maxZoom: 19 }).addTo(map)

    map.on('click', (event: L.LeafletMouseEvent) => {
      const { lat, lng } = event.latlng
      // Leaflet reports longitudes outside ±180 after horizontal wrapping.
      onChangeRef.current({ latitude: lat, longitude: L.latLng(lat, lng).wrap().lng })
    })

    mapRef.current = map
    markerRef.current = L.marker(PREVIEW_CENTRE, { icon })

    // The container is often laid out after the map mounts (inside a panel or
    // a tab); without this the tiles render into a zero-height box.
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(container)

    return () => {
      observer.disconnect()
      map.remove()
      mapRef.current = null
      markerRef.current = null
    }
  }, [])

  // Sync the marker to the current value, including the initial value that
  // arrives once an edited project's query resolves.
  useEffect(() => {
    const map = mapRef.current
    const marker = markerRef.current
    if (!map || !marker) return
    if (!value) {
      marker.remove()
      return
    }
    const point: [number, number] = [value.latitude, value.longitude]
    marker.setLatLng(point).addTo(map)
    map.setView(point, Math.max(map.getZoom(), PICKED_ZOOM))
  }, [value])

  useEffect(() => {
    const container = containerRef.current
    // CSS-module lookups are typed as possibly undefined; skip rather than
    // toggling an "undefined" class name onto the element.
    if (container && styles.disabled) container.classList.toggle(styles.disabled, disabled)
  }, [disabled])

  return (
    <div className={styles.wrapper}>
      {label && (
        <p className={styles.label} id={headingId}>
          {label}
        </p>
      )}
      {hint && <p className={styles.hint}>{hint}</p>}
      <div
        ref={containerRef}
        className={styles.map}
        role="application"
        aria-label={label ?? 'خريطة تحديد الموقع'}
        aria-describedby={hint ? headingId : undefined}
        data-testid="location-picker-map"
      />
      <p className={styles.readout} data-testid="location-picker-readout" dir="ltr">
        {value
          ? `${value.latitude.toFixed(6)}, ${value.longitude.toFixed(6)}`
          : '—'}
      </p>
    </div>
  )
}
