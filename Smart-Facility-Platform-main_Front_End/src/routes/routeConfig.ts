import type { Role } from '@/types'
import type { IconName } from '@/components/icons'

/**
 * The single source of truth for navigation.
 *
 * The sidebar, the breadcrumb trail and the route tree are all derived from
 * this one structure. In the static prototype those were three separate
 * hardcoded lists that drifted apart; here, adding a page means adding one
 * entry and the nav, the crumbs and the URL all agree by construction.
 */

export interface NavItem {
  /** Absolute path — matches the route tree exactly. */
  path: string
  label: string
  icon: IconName
}

export interface NavGroup {
  title: string
  items: NavItem[]
}

export interface RoleRoutes {
  basePath: string
  homePath: string
  searchPlaceholder: string
  nav: NavGroup[]
}

export const ROLE_ROUTES: Record<Role, RoleRoutes> = {
  super_admin: {
    basePath: '/admin',
    homePath: '/admin/dashboard',
    searchPlaceholder: 'ابحث عن مشروع، مستخدم، أو تقرير…',
    nav: [
      {
        title: 'نظرة عامة',
        items: [
          { path: '/admin/dashboard', label: 'لوحة القيادة التنفيذية', icon: 'dashboard' },
          { path: '/admin/projects', label: 'المشاريع', icon: 'projects' },
          { path: '/admin/users', label: 'المستخدمون', icon: 'users' },
          { path: '/admin/roles', label: 'الأدوار والصلاحيات', icon: 'permissions' },
        ],
      },
      {
        title: 'النظام',
        items: [
          { path: '/admin/reports', label: 'مركز التقارير', icon: 'reports' },
          { path: '/admin/analytics', label: 'التحليلات', icon: 'analytics' },
          { path: '/admin/notifications', label: 'مركز الإشعارات', icon: 'notifications' },
          { path: '/admin/audit-logs', label: 'سجل التدقيق', icon: 'audit' },
          { path: '/admin/settings', label: 'إعدادات النظام', icon: 'settings' },
        ],
      },
    ],
  },

  construction_manager: {
    basePath: '/construction',
    homePath: '/construction/dashboard',
    searchPlaceholder: 'ابحث عن مشروع، مرحلة، أو مادة…',
    nav: [
      {
        title: 'نظرة عامة',
        items: [
          { path: '/construction/dashboard', label: 'لوحة التحكم الإنشائية', icon: 'dashboard' },
          { path: '/construction/projects', label: 'المشاريع الإنشائية', icon: 'projects' },
        ],
      },
      {
        title: 'التنفيذ والجدولة',
        items: [
          { path: '/construction/stages', label: 'مراحل التنفيذ', icon: 'stages' },
          { path: '/construction/progress', label: 'متابعة التقدم', icon: 'progress' },
          { path: '/construction/timeline', label: 'الجدول الزمني', icon: 'calendar' },
        ],
      },
      {
        title: 'الموارد',
        items: [
          { path: '/construction/materials', label: 'إدارة المواد', icon: 'materials' },
          {
            path: '/construction/material-requests',
            label: 'طلبات المواد',
            icon: 'materialRequests',
          },
        ],
      },
      {
        title: 'الجودة والتوثيق',
        items: [
          { path: '/construction/quality', label: 'فحوصات الجودة', icon: 'quality' },
          { path: '/construction/daily-reports', label: 'التقارير اليومية', icon: 'reports' },
          { path: '/construction/documents', label: 'الوثائق والملفات', icon: 'documents' },
          { path: '/construction/photos', label: 'صور الموقع', icon: 'camera' },
        ],
      },
    ],
  },

  operations_manager: {
    basePath: '/operations',
    homePath: '/operations/dashboard',
    searchPlaceholder: 'ابحث عن منشأة، أصل، أو أمر صيانة…',
    nav: [
      {
        title: 'نظرة عامة',
        items: [
          { path: '/operations/dashboard', label: 'لوحة التشغيل الرئيسية', icon: 'dashboard' },
        ],
      },
      {
        title: 'المنشآت والأصول',
        items: [
          { path: '/operations/facilities', label: 'المنشآت', icon: 'facilities' },
          { path: '/operations/assets', label: 'إدارة الأصول', icon: 'assets' },
          { path: '/operations/asset-health', label: 'مركز صحة الأصول', icon: 'assetHealth' },
        ],
      },
      {
        title: 'الصيانة',
        items: [
          { path: '/operations/work-orders', label: 'أوامر الصيانة', icon: 'maintenance' },
          { path: '/operations/preventive', label: 'الصيانة الوقائية', icon: 'preventive' },
          { path: '/operations/corrective', label: 'الصيانة التصحيحية', icon: 'corrective' },
          { path: '/operations/calendar', label: 'تقويم الصيانة', icon: 'calendar' },
        ],
      },
      {
        title: 'الأداء والتقارير',
        items: [
          { path: '/operations/faults', label: 'تتبع الأعطال', icon: 'faults' },
          { path: '/operations/performance', label: 'كفاءة أداء المنشآت', icon: 'analytics' },
          { path: '/operations/reports', label: 'التقارير التشغيلية', icon: 'reports' },
        ],
      },
    ],
  },

  security_officer: {
    basePath: '/security',
    homePath: '/security/dashboard',
    searchPlaceholder: 'ابحث عن تنبيه، حادث، أو موقع…',
    nav: [
      {
        title: 'نظرة عامة',
        items: [{ path: '/security/dashboard', label: 'لوحة التحكم الأمنية', icon: 'dashboard' }],
      },
      {
        title: 'المراقبة والتنبيه',
        items: [
          { path: '/security/alerts', label: 'التنبيهات الحيّة', icon: 'securityAlert' },
          { path: '/security/alert-history', label: 'سجل التنبيهات', icon: 'eventLog' },
          { path: '/security/cameras', label: 'مراقبة الكاميرات', icon: 'camera' },
          { path: '/security/emergency', label: 'المراقبة الطارئة', icon: 'emergency' },
        ],
      },
      {
        title: 'الحوادث والاستجابة',
        items: [
          { path: '/security/incidents', label: 'إدارة الحوادث', icon: 'incidents' },
          { path: '/security/response', label: 'مركز الاستجابة', icon: 'response' },
        ],
      },
      {
        title: 'التحليلات والتقارير',
        items: [
          { path: '/security/analytics', label: 'تحليلات الحوادث', icon: 'analytics' },
          { path: '/security/reports', label: 'التقارير الأمنية', icon: 'reports' },
        ],
      },
      {
        title: 'التوثيق',
        items: [{ path: '/security/documents', label: 'وثائق السلامة', icon: 'documents' }],
      },
    ],
  },
}

/** Flat list of every nav item for a role — used by breadcrumbs. */
export function navItemsFor(role: Role): NavItem[] {
  return ROLE_ROUTES[role].nav.flatMap((group) => group.items)
}

/**
 * Finds the nav entry a URL belongs to, including drill-down pages:
 * `/admin/projects/prj-001/edit` resolves to the "المشاريع" nav item, so the
 * sidebar highlights and the breadcrumb trail both stay correct on detail pages.
 */
export function activeNavItem(role: Role, pathname: string): NavItem | undefined {
  const items = navItemsFor(role)
  return (
    items.find((item) => item.path === pathname) ??
    items
      .filter((item) => pathname.startsWith(`${item.path}/`))
      // Longest match wins, so /admin/projects beats /admin.
      .sort((a, b) => b.path.length - a.path.length)[0]
  )
}
