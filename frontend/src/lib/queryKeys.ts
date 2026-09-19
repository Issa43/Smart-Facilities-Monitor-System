/**
 * Every TanStack Query key in the app, in one place.
 *
 * Pages call `useQuery` directly rather than going through a wrapper hook per
 * endpoint — one less layer to trace through. This file is what keeps that
 * from turning into scattered string literals: a mutation invalidates
 * `qk.projects.all` and every project query refetches, with no guessing about
 * which key string some page happened to use.
 */
export const qk = {
  auth: {
    session: ['auth', 'session'] as const,
  },
  users: {
    all: ['users'] as const,
    list: (search?: string) => ['users', 'list', search ?? ''] as const,
    detail: (id: string) => ['users', 'detail', id] as const,
  },
  projects: {
    all: ['projects'] as const,
    list: (managerId?: string) => ['projects', 'list', managerId ?? 'all'] as const,
    detail: (id: string) => ['projects', 'detail', id] as const,
  },
  stages: {
    all: ['stages'] as const,
    byProject: (projectId: string) => ['stages', 'project', projectId] as const,
    detail: (id: string) => ['stages', 'detail', id] as const,
    updates: (stageId: string) => ['stages', 'updates', stageId] as const,
  },
  materials: {
    all: ['materials'] as const,
    byProject: (projectId?: string) => ['materials', 'project', projectId ?? 'all'] as const,
    requests: (projectId?: string) => ['materials', 'requests', projectId ?? 'all'] as const,
  },
  quality: {
    inspections: (projectId?: string) => ['quality', 'inspections', projectId ?? 'all'] as const,
  },
  dailyReports: {
    all: (projectId?: string) => ['daily-reports', projectId ?? 'all'] as const,
    detail: (id: string) => ['daily-reports', 'detail', id] as const,
  },
  documents: {
    all: (projectId?: string) => ['documents', projectId ?? 'all'] as const,
  },
  sitePhotos: {
    all: (projectId?: string) => ['site-photos', projectId ?? 'all'] as const,
  },
  facilities: {
    all: ['facilities'] as const,
    list: ['facilities', 'list'] as const,
    detail: (id: string) => ['facilities', 'detail', id] as const,
  },
  assets: {
    all: ['assets'] as const,
    list: (facilityId?: string) => ['assets', 'list', facilityId ?? 'all'] as const,
    detail: (id: string) => ['assets', 'detail', id] as const,
  },
  workOrders: {
    all: ['work-orders'] as const,
    list: (facilityId?: string) => ['work-orders', 'list', facilityId ?? 'all'] as const,
    detail: (id: string) => ['work-orders', 'detail', id] as const,
  },
  faults: {
    all: ['faults'] as const,
    list: (facilityId?: string) => ['faults', 'list', facilityId ?? 'all'] as const,
    detail: (id: string) => ['faults', 'detail', id] as const,
  },
  alerts: {
    all: ['alerts'] as const,
    list: ['alerts', 'list'] as const,
    detail: (id: string) => ['alerts', 'detail', id] as const,
  },
  cameraEvents: {
    all: ['camera-events'] as const,
    list: ['camera-events', 'list'] as const,
    detail: (id: string) => ['camera-events', 'detail', id] as const,
  },
  incidents: {
    all: ['incidents'] as const,
    list: ['incidents', 'list'] as const,
    detail: (id: string) => ['incidents', 'detail', id] as const,
  },
  notifications: {
    all: ['notifications'] as const,
    list: (role: string) => ['notifications', 'list', role] as const,
  },
  auditLogs: {
    all: ['audit-logs'] as const,
  },
  reports: {
    all: ['reports'] as const,
    generated: ['reports', 'generated'] as const,
  },
  safety: {
    all: ['safety'] as const,
    alerts: ['safety', 'alerts'] as const,
    /** Prefix for every alert list page; does not match alert detail queries. */
    alertLists: ['safety', 'alerts', 'list'] as const,
    alertList: (filters: object) => ['safety', 'alerts', 'list', filters] as const,
    alertDetail: (id: string) => ['safety', 'alerts', 'detail', id] as const,
    hazardEvents: (filters: object) => ['safety', 'hazard-events', 'list', filters] as const,
    hazardEventDetail: (id: string) => ['safety', 'hazard-events', 'detail', id] as const,
    coverage: ['safety', 'coverage'] as const,
  },
  stats: {
    admin: ['stats', 'admin'] as const,
    construction: (managerId: string) => ['stats', 'construction', managerId] as const,
    operations: ['stats', 'operations'] as const,
    security: ['stats', 'security'] as const,
  },
} as const
