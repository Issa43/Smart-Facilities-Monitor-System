import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/**
 * The brand icon set, ported from the prototype's nav-config.js.
 *
 * Grammar — do not break it when adding icons:
 *   · 24×24 grid, 1.6px rounded stroke (from `svg.gi` in base.css)
 *   · cool-gray-blue as the primary line colour
 *   · a secondary detail stroked in --babyblue
 *   · exactly one purple "connection node" dot per icon (.node), or crimson
 *     (.node-critical) when the icon represents something critical
 *
 * That two-tone rule is what makes the set look designed rather than assembled,
 * and it is why these are hand-drawn instead of pulled from a stock library.
 * lucide-react covers generic UI chrome (chevrons, close, upload) where no
 * brand identity is at stake.
 */

export type IconName =
  | 'dashboard'
  | 'projects'
  | 'users'
  | 'permissions'
  | 'stages'
  | 'progress'
  | 'materials'
  | 'materialRequests'
  | 'quality'
  | 'reports'
  | 'documents'
  | 'facilities'
  | 'assets'
  | 'assetHealth'
  | 'maintenance'
  | 'preventive'
  | 'corrective'
  | 'workOrders'
  | 'faults'
  | 'securityAlert'
  | 'emergency'
  | 'incidents'
  | 'response'
  | 'eventLog'
  | 'notifications'
  | 'settings'
  | 'analytics'
  | 'audit'
  | 'camera'
  | 'calendar'

const PATHS: Record<IconName, ReactNode> = {
  dashboard: (
    <>
      <rect x="4" y="4" width="7" height="7" rx="1.5" fill="var(--primary-tint)" />
      <rect x="13" y="4" width="7" height="7" rx="1.5" />
      <rect x="4" y="13" width="7" height="7" rx="1.5" />
      <rect x="13" y="13" width="7" height="7" rx="1.5" fill="var(--primary-tint)" />
    </>
  ),
  projects: (
    <>
      <rect x="4" y="8" width="13" height="11" rx="2" fill="var(--primary-tint)" />
      <rect x="7" y="5" width="13" height="11" rx="2" />
      <circle className="node" cx="20" cy="5" r="1.8" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.5 20c.6-4 2.7-6 5.5-6s4.9 2 5.5 6" stroke="var(--babyblue)" />
      <circle cx="17" cy="7" r="2.4" stroke="var(--coolgray-soft)" />
      <path d="M15 20c.3-2.6 1.6-4.2 3-4.6" stroke="var(--coolgray-soft)" />
    </>
  ),
  permissions: (
    <>
      <circle cx="9" cy="9" r="5" />
      <path d="M12.3 12.3 20 20M16 16l2-2M19 19l2-2" stroke="var(--primary)" />
      <circle className="node" cx="9" cy="9" r="1.5" />
    </>
  ),
  stages: (
    <>
      <rect x="4" y="15" width="4" height="5" rx="1" />
      <rect x="10" y="10" width="4" height="10" rx="1" />
      <rect
        x="16"
        y="5"
        width="4"
        height="15"
        rx="1"
        fill="var(--primary-tint)"
        stroke="var(--primary)"
      />
      <circle className="node" cx="18" cy="3" r="1.8" />
    </>
  ),
  progress: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 6v6l4 2" stroke="var(--babyblue)" />
      <circle className="node" cx="12" cy="12" r="1.4" />
    </>
  ),
  materials: (
    <>
      <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z" />
      <path d="M12 3v9m0 9v-9m-8-4.5L12 12l8-4.5" stroke="var(--babyblue)" />
      <circle className="node" cx="12" cy="12" r="1.5" />
    </>
  ),
  materialRequests: (
    <>
      <rect x="6" y="4" width="12" height="17" rx="2" />
      <rect x="9" y="2.5" width="6" height="3" rx="1" />
      <path d="M9 11h6M9 15h4" stroke="var(--babyblue)" />
      <circle className="node" cx="17" cy="17" r="1.8" />
    </>
  ),
  quality: (
    <>
      <path d="M12 3l7 3v6c0 5-3 8-7 9-4-1-7-4-7-9V6l7-3z" fill="var(--success-tint)" />
      <path d="M9 12l2 2 4-4.5" stroke="var(--success)" />
      <circle className="node" cx="18" cy="6" r="1.8" />
    </>
  ),
  reports: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="3" />
      <path d="M8 15V10M12 15V7M16 15v-3.5" stroke="var(--primary)" />
      <circle className="node" cx="19" cy="5" r="1.8" />
    </>
  ),
  documents: (
    <>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z" />
      <path d="M14 3v5h5" stroke="var(--babyblue)" />
      <circle className="node" cx="17" cy="19" r="1.8" />
    </>
  ),
  facilities: (
    <>
      <rect x="4" y="6" width="16" height="15" rx="2" />
      <path d="M4 11h16M9 6V4m6 2V4" stroke="var(--babyblue)" />
      <circle className="node" cx="19" cy="4" r="1.8" />
    </>
  ),
  assets: (
    <>
      <path d="M12 3l7 4v10l-7 4-7-4V7l7-4z" />
      <path d="M5 7l7 4 7-4M12 11v10" stroke="var(--babyblue)" />
      <circle className="node" cx="12" cy="11" r="1.6" />
    </>
  ),
  assetHealth: (
    <>
      <circle cx="12" cy="12" r="7" />
      <path d="M12 8v4l2.5 2.5" stroke="var(--babyblue)" />
      <circle className="node" cx="12" cy="12" r="1.6" />
    </>
  ),
  maintenance: (
    <>
      <circle cx="12" cy="12" r="4.5" />
      <path
        d="M12 3v2.4M12 18.6V21M21 12h-2.4M5.4 12H3M18.5 5.5l-1.7 1.7M7.2 16.8l-1.7 1.7M18.5 18.5l-1.7-1.7M7.2 7.2 5.5 5.5"
        stroke="var(--babyblue)"
      />
      <circle className="node" cx="12" cy="12" r="1.5" />
    </>
  ),
  preventive: (
    <>
      <path d="M4 12a8 8 0 0 1 14-5" />
      <path d="M20 12a8 8 0 0 1-14 5" stroke="var(--babyblue)" />
      <path d="M18 4v4h-4M6 20v-4h4" />
      <circle className="node" cx="18" cy="4" r="1.5" />
    </>
  ),
  corrective: (
    <>
      <path d="M14.5 6.5l3 3L9 18l-4 1 1-4z" />
      <path d="M13 8l3 3" stroke="var(--babyblue)" />
      <circle className="node" cx="19" cy="5" r="1.6" />
    </>
  ),
  workOrders: (
    <>
      <rect x="6" y="4" width="12" height="17" rx="2" />
      <rect x="9" y="2.5" width="6" height="3" rx="1" />
      <path d="M9 11h6M9 15h4" stroke="var(--babyblue)" />
      <circle className="node" cx="17" cy="17" r="1.8" />
    </>
  ),
  faults: (
    <>
      <path d="M12 3l8.5 3.5v6c0 5.5-3.6 8.5-8.5 10.5-4.9-2-8.5-5-8.5-10.5v-6L12 3z" />
      <path d="M12 9v5" stroke="var(--critical)" />
      <circle className="node-critical" cx="12" cy="17" r="1.1" />
    </>
  ),
  securityAlert: (
    <>
      <path d="M12 3l8.5 3.5v6c0 5.5-3.6 8.5-8.5 10.5-4.9-2-8.5-5-8.5-10.5v-6L12 3z" />
      <path d="M12 9v5" stroke="var(--critical)" />
      <circle className="node-critical" cx="12" cy="17" r="1.1" />
    </>
  ),
  emergency: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5v5.5" stroke="var(--critical)" />
      <circle className="node-critical" cx="12" cy="16.5" r="1.2" />
    </>
  ),
  incidents: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path
        d="M12 3.5 13.4 10 20 12l-6.6 2-1.4 6.5L10.6 14 4 12l6.6-2z"
        fill="var(--critical-tint)"
        stroke="var(--critical)"
      />
      <circle className="node-critical" cx="12" cy="12" r="1.1" />
    </>
  ),
  response: (
    <>
      <path d="M5 13l4 4L19 7" />
      <circle cx="12" cy="12" r="9" stroke="var(--babyblue)" />
      <circle className="node" cx="19" cy="5" r="1.6" />
    </>
  ),
  eventLog: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="3" />
      <path d="M8 9h8M8 13h8M8 17h5" stroke="var(--babyblue)" />
      <circle className="node" cx="19" cy="5" r="1.6" />
    </>
  ),
  notifications: (
    <>
      <path d="M6 10a6 6 0 0 1 12 0v4l2 3H4l2-3v-4z" />
      <path d="M10 20a2.2 2.2 0 0 0 4 0" stroke="var(--babyblue)" />
      <circle className="node" cx="18" cy="7" r="1.6" />
    </>
  ),
  settings: (
    <>
      <path d="M4 7h10M4 12h16M4 17h7" />
      <circle cx="16" cy="7" r="2.1" fill="var(--primary-tint)" stroke="var(--primary)" />
      <circle cx="9" cy="17" r="2.1" fill="var(--accent-tint)" stroke="var(--accent)" />
      <circle className="node" cx="20" cy="12" r="1.5" />
    </>
  ),
  analytics: (
    <>
      <path d="M4 19V9M9 19V5M14 19v-7M19 19v-4" stroke="var(--coolgray)" />
      <path d="M3 19h18" stroke="var(--babyblue)" />
      <circle className="node" cx="9" cy="5" r="1.7" />
    </>
  ),
  audit: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="3" />
      <path d="M8 9h8M8 13h8M8 17h5" />
      <circle className="node" cx="19" cy="5" r="1.8" />
    </>
  ),
  camera: (
    <>
      <path d="M3 8.5l13-3.5 1.5 5.5-13 3.5z" />
      <path d="M6 13v5M4 18h5" stroke="var(--babyblue)" />
      <circle cx="19.5" cy="13" r="2.4" stroke="var(--coolgray-soft)" />
      <circle className="node" cx="19.5" cy="13" r="1" />
    </>
  ),
  calendar: (
    <>
      <rect x="3.5" y="5" width="17" height="16" rx="2.5" />
      <path d="M3.5 10h17M8 3v4M16 3v4" stroke="var(--babyblue)" />
      <circle className="node" cx="16.5" cy="15.5" r="1.6" />
    </>
  ),
}

interface IconProps {
  name: IconName
  size?: number
  className?: string
  /** Provide when the icon is the only content of a control; omit when a text label sits beside it. */
  title?: string
}

export function Icon({ name, size = 20, className, title }: IconProps) {
  return (
    <svg
      className={cn('gi', className)}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {PATHS[name]}
    </svg>
  )
}

/** The platform mark — used in the sidebar, the login panel, and the favicon. */
export function BrandMark({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <circle cx="20" cy="20" r="17" stroke="var(--border)" strokeWidth="2.5" />
      <path
        d="M20 3 A17 17 0 0 1 35.4 12.5"
        stroke="var(--primary)"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <path
        d="M35.4 12.5 A17 17 0 0 1 33 30.5"
        stroke="var(--accent)"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <path
        d="M33 30.5 A17 17 0 0 1 15 36.6"
        stroke="var(--success)"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <rect x="14" y="15" width="12" height="11" rx="1.5" fill="var(--primary)" opacity="0.15" />
      <rect x="16.5" y="17.5" width="3" height="3" fill="var(--primary)" />
      <rect x="20.5" y="17.5" width="3" height="3" fill="var(--primary)" />
      <rect x="16.5" y="21.5" width="3" height="3" fill="var(--accent)" />
      <rect x="20.5" y="21.5" width="3" height="3" fill="var(--primary)" />
    </svg>
  )
}
