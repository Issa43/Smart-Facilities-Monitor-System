import { Suspense, lazy } from 'react'
import { Route, Routes } from 'react-router-dom'
import { AuthenticatedRoute, HomeRedirect, ProtectedRoute } from '@/routes/ProtectedRoute'
import { RouteFallback } from '@/routes/RouteFallback'

const LoginPage = lazy(() =>
  import('@/features/auth/pages/LoginPage').then((m) => ({ default: m.LoginPage })),
)
const ForgotPasswordPage = lazy(() =>
  import('@/features/auth/pages/ForgotPasswordPage').then((m) => ({
    default: m.ForgotPasswordPage,
  })),
)
const ResetPasswordPage = lazy(() =>
  import('@/features/auth/pages/ResetPasswordPage').then((m) => ({ default: m.ResetPasswordPage })),
)
const ResetPasswordSuccessPage = lazy(() =>
  import('@/features/auth/pages/ResetPasswordSuccessPage').then((m) => ({
    default: m.ResetPasswordSuccessPage,
  })),
)

const AdminDashboardPage = lazy(() =>
  import('@/features/super-admin/pages/AdminDashboardPage').then((m) => ({
    default: m.AdminDashboardPage,
  })),
)
const AdminProjectsPage = lazy(() =>
  import('@/features/super-admin/pages/AdminProjectsPage').then((m) => ({
    default: m.AdminProjectsPage,
  })),
)
const ProjectFormPage = lazy(() =>
  import('@/features/super-admin/pages/ProjectFormPage').then((m) => ({
    default: m.ProjectFormPage,
  })),
)
const AdminUsersPage = lazy(() =>
  import('@/features/super-admin/pages/AdminUsersPage').then((m) => ({
    default: m.AdminUsersPage,
  })),
)
const AdminUserDetailPage = lazy(() =>
  import('@/features/super-admin/pages/AdminUserDetailPage').then((m) => ({
    default: m.AdminUserDetailPage,
  })),
)
const AdminRolesPage = lazy(() =>
  import('@/features/super-admin/pages/AdminRolesPage').then((m) => ({
    default: m.AdminRolesPage,
  })),
)
const AdminReportsPage = lazy(() =>
  import('@/features/super-admin/pages/AdminReportsPage').then((m) => ({
    default: m.AdminReportsPage,
  })),
)
const AdminAnalyticsPage = lazy(() =>
  import('@/features/super-admin/pages/AdminAnalyticsPage').then((m) => ({
    default: m.AdminAnalyticsPage,
  })),
)
const AdminAuditLogsPage = lazy(() =>
  import('@/features/super-admin/pages/AdminAuditLogsPage').then((m) => ({
    default: m.AdminAuditLogsPage,
  })),
)
const AdminSettingsPage = lazy(() =>
  import('@/features/super-admin/pages/AdminSettingsPage').then((m) => ({
    default: m.AdminSettingsPage,
  })),
)

const ConstructionDashboardPage = lazy(() =>
  import('@/features/construction/pages/ConstructionDashboardPage').then((m) => ({
    default: m.ConstructionDashboardPage,
  })),
)
const ConstructionProjectsPage = lazy(() =>
  import('@/features/construction/pages/ConstructionProjectsPage').then((m) => ({
    default: m.ConstructionProjectsPage,
  })),
)
const StagesPage = lazy(() =>
  import('@/features/construction/pages/StagesPage').then((m) => ({ default: m.StagesPage })),
)
const StageDetailPage = lazy(() =>
  import('@/features/construction/pages/StageDetailPage').then((m) => ({
    default: m.StageDetailPage,
  })),
)
const ProgressPage = lazy(() =>
  import('@/features/construction/pages/ProgressPage').then((m) => ({ default: m.ProgressPage })),
)
const TimelinePage = lazy(() =>
  import('@/features/construction/pages/TimelinePage').then((m) => ({ default: m.TimelinePage })),
)
const MaterialsPage = lazy(() =>
  import('@/features/construction/pages/MaterialsPage').then((m) => ({ default: m.MaterialsPage })),
)
const MaterialRequestsPage = lazy(() =>
  import('@/features/construction/pages/MaterialRequestsPage').then((m) => ({
    default: m.MaterialRequestsPage,
  })),
)
const CreateMaterialRequestPage = lazy(() =>
  import('@/features/construction/pages/CreateMaterialRequestPage').then((m) => ({
    default: m.CreateMaterialRequestPage,
  })),
)
const QualityInspectionsPage = lazy(() =>
  import('@/features/construction/pages/QualityInspectionsPage').then((m) => ({
    default: m.QualityInspectionsPage,
  })),
)
const DailyReportsPage = lazy(() =>
  import('@/features/construction/pages/DailyReportsPage').then((m) => ({
    default: m.DailyReportsPage,
  })),
)
const DocumentsPage = lazy(() =>
  import('@/features/construction/pages/DocumentsPage').then((m) => ({ default: m.DocumentsPage })),
)
const SitePhotosPage = lazy(() =>
  import('@/features/construction/pages/SitePhotosPage').then((m) => ({
    default: m.SitePhotosPage,
  })),
)

const OperationsDashboardPage = lazy(() =>
  import('@/features/operations/pages/OperationsDashboardPage').then((m) => ({
    default: m.OperationsDashboardPage,
  })),
)
const FacilitiesPage = lazy(() =>
  import('@/features/operations/pages/FacilitiesPage').then((m) => ({ default: m.FacilitiesPage })),
)
const FacilityDetailPage = lazy(() =>
  import('@/features/operations/pages/FacilityDetailPage').then((m) => ({
    default: m.FacilityDetailPage,
  })),
)
const AssetsPage = lazy(() =>
  import('@/features/operations/pages/AssetsPage').then((m) => ({ default: m.AssetsPage })),
)
const AssetDetailPage = lazy(() =>
  import('@/features/operations/pages/AssetDetailPage').then((m) => ({
    default: m.AssetDetailPage,
  })),
)
const AssetHealthPage = lazy(() =>
  import('@/features/operations/pages/AssetHealthPage').then((m) => ({
    default: m.AssetHealthPage,
  })),
)
const WorkOrdersPage = lazy(() =>
  import('@/features/operations/pages/WorkOrdersPage').then((m) => ({ default: m.WorkOrdersPage })),
)
const WorkOrderDetailPage = lazy(() =>
  import('@/features/operations/pages/WorkOrderDetailPage').then((m) => ({
    default: m.WorkOrderDetailPage,
  })),
)
const MaintenanceCalendarPage = lazy(() =>
  import('@/features/operations/pages/MaintenanceCalendarPage').then((m) => ({
    default: m.MaintenanceCalendarPage,
  })),
)
const FaultTrackingPage = lazy(() =>
  import('@/features/operations/pages/FaultTrackingPage').then((m) => ({
    default: m.FaultTrackingPage,
  })),
)
const FacilityPerformancePage = lazy(() =>
  import('@/features/operations/pages/FacilityPerformancePage').then((m) => ({
    default: m.FacilityPerformancePage,
  })),
)
const OperationalReportsPage = lazy(() =>
  import('@/features/operations/pages/OperationalReportsPage').then((m) => ({
    default: m.OperationalReportsPage,
  })),
)

const SecurityDashboardPage = lazy(() =>
  import('@/features/security/pages/SecurityDashboardPage').then((m) => ({
    default: m.SecurityDashboardPage,
  })),
)
const AlertsPage = lazy(() =>
  import('@/features/security/pages/AlertsPage').then((m) => ({ default: m.AlertsPage })),
)
const AlertDetailPage = lazy(() =>
  import('@/features/security/pages/AlertDetailPage').then((m) => ({ default: m.AlertDetailPage })),
)
const AlertHistoryPage = lazy(() =>
  import('@/features/security/pages/AlertHistoryPage').then((m) => ({
    default: m.AlertHistoryPage,
  })),
)
const IncidentsPage = lazy(() =>
  import('@/features/security/pages/IncidentsPage').then((m) => ({ default: m.IncidentsPage })),
)
const IncidentDetailPage = lazy(() =>
  import('@/features/security/pages/IncidentDetailPage').then((m) => ({
    default: m.IncidentDetailPage,
  })),
)
const ResponseCenterPage = lazy(() =>
  import('@/features/security/pages/ResponseCenterPage').then((m) => ({
    default: m.ResponseCenterPage,
  })),
)
const EmergencyMonitoringPage = lazy(() =>
  import('@/features/security/pages/EmergencyMonitoringPage').then((m) => ({
    default: m.EmergencyMonitoringPage,
  })),
)
const CameraMonitoringPage = lazy(() =>
  import('@/features/security/pages/CameraMonitoringPage').then((m) => ({
    default: m.CameraMonitoringPage,
  })),
)
const IncidentAnalyticsPage = lazy(() =>
  import('@/features/security/pages/IncidentAnalyticsPage').then((m) => ({
    default: m.IncidentAnalyticsPage,
  })),
)
const SecurityReportsPage = lazy(() =>
  import('@/features/security/pages/SecurityReportsPage').then((m) => ({
    default: m.SecurityReportsPage,
  })),
)
const SafetyDocumentationPage = lazy(() =>
  import('@/features/security/pages/SafetyDocumentationPage').then((m) => ({
    default: m.SafetyDocumentationPage,
  })),
)

const ProjectDetailPage = lazy(() =>
  import('@/features/shared/ProjectDetailPage').then((m) => ({ default: m.ProjectDetailPage })),
)
const NotificationsPage = lazy(() =>
  import('@/features/shared/NotificationsPage').then((m) => ({ default: m.NotificationsPage })),
)
const ProfilePage = lazy(() =>
  import('@/features/shared/pages/ProfilePage').then((m) => ({ default: m.ProfilePage })),
)
const HelpPage = lazy(() =>
  import('@/features/shared/pages/HelpPage').then((m) => ({ default: m.HelpPage })),
)
const NotFoundPage = lazy(() =>
  import('@/features/shared/pages/NotFoundPage').then((m) => ({ default: m.NotFoundPage })),
)

/**
 * The route tree. Paths mirror routes/routeConfig.ts exactly — that file drives
 * the sidebar and breadcrumbs, this one decides what renders.
 */
export function App() {
  return (
    // Every page is lazy-loaded, so the login screen does not download the
    // charting library or three roles' worth of pages it will never render.
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        {/* ---------- Public ---------- */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/reset-password/success" element={<ResetPasswordSuccessPage />} />

        <Route path="/" element={<HomeRedirect />} />

        {/* ---------- Super Admin ---------- */}
        <Route element={<ProtectedRoute role="super_admin" />}>
          <Route path="/admin/dashboard" element={<AdminDashboardPage />} />
          <Route path="/admin/projects" element={<AdminProjectsPage />} />
          <Route path="/admin/projects/new" element={<ProjectFormPage mode="create" />} />
          <Route
            path="/admin/projects/:projectId"
            element={<ProjectDetailPage basePath="/admin" role="super_admin" />}
          />
          <Route path="/admin/projects/:projectId/edit" element={<ProjectFormPage mode="edit" />} />
          <Route path="/admin/users" element={<AdminUsersPage />} />
          <Route path="/admin/users/:userId" element={<AdminUserDetailPage />} />
          <Route path="/admin/roles" element={<AdminRolesPage />} />
          <Route path="/admin/reports" element={<AdminReportsPage />} />
          <Route path="/admin/analytics" element={<AdminAnalyticsPage />} />
          <Route path="/admin/notifications" element={<NotificationsPage />} />
          <Route path="/admin/audit-logs" element={<AdminAuditLogsPage />} />
          <Route path="/admin/settings" element={<AdminSettingsPage />} />
        </Route>

        {/* ---------- Construction Manager ---------- */}
        <Route element={<ProtectedRoute role="construction_manager" />}>
          <Route path="/construction/dashboard" element={<ConstructionDashboardPage />} />
          <Route path="/construction/projects" element={<ConstructionProjectsPage />} />
          <Route
            path="/construction/projects/:projectId"
            element={<ProjectDetailPage basePath="/construction" role="construction_manager" />}
          />
          <Route path="/construction/stages" element={<StagesPage />} />
          <Route path="/construction/stages/:stageId" element={<StageDetailPage />} />
          <Route path="/construction/progress" element={<ProgressPage />} />
          <Route path="/construction/timeline" element={<TimelinePage />} />
          <Route path="/construction/materials" element={<MaterialsPage />} />
          <Route path="/construction/material-requests" element={<MaterialRequestsPage />} />
          <Route
            path="/construction/material-requests/new"
            element={<CreateMaterialRequestPage />}
          />
          <Route path="/construction/quality" element={<QualityInspectionsPage />} />
          <Route path="/construction/daily-reports" element={<DailyReportsPage />} />
          <Route path="/construction/documents" element={<DocumentsPage />} />
          <Route path="/construction/photos" element={<SitePhotosPage />} />
        </Route>

        {/* ---------- Operations Manager ---------- */}
        <Route element={<ProtectedRoute role="operations_manager" />}>
          <Route path="/operations/dashboard" element={<OperationsDashboardPage />} />
          <Route path="/operations/facilities" element={<FacilitiesPage />} />
          <Route path="/operations/facilities/:facilityId" element={<FacilityDetailPage />} />
          <Route path="/operations/assets" element={<AssetsPage />} />
          <Route path="/operations/assets/:assetId" element={<AssetDetailPage />} />
          <Route path="/operations/asset-health" element={<AssetHealthPage />} />
          <Route path="/operations/work-orders" element={<WorkOrdersPage />} />
          <Route path="/operations/work-orders/:orderId" element={<WorkOrderDetailPage />} />
          <Route
            path="/operations/preventive"
            element={
              <WorkOrdersPage
                maintenanceType="preventive"
                title="الصيانة الوقائية"
                description="أوامر الصيانة المجدولة دورياً للحفاظ على كفاءة الأصول ومنع الأعطال قبل وقوعها."
              />
            }
          />
          <Route
            path="/operations/corrective"
            element={
              <WorkOrdersPage
                maintenanceType="corrective"
                title="الصيانة التصحيحية"
                description="أوامر الإصلاح غير المخططة الناتجة عن أعطال فعلية في الأصول التشغيلية."
              />
            }
          />
          <Route path="/operations/calendar" element={<MaintenanceCalendarPage />} />
          <Route path="/operations/faults" element={<FaultTrackingPage />} />
          <Route path="/operations/performance" element={<FacilityPerformancePage />} />
          <Route path="/operations/reports" element={<OperationalReportsPage />} />
        </Route>

        {/* ---------- Security Officer ---------- */}
        <Route element={<ProtectedRoute role="security_officer" />}>
          <Route path="/security/dashboard" element={<SecurityDashboardPage />} />
          <Route path="/security/alerts" element={<AlertsPage />} />
          <Route path="/security/alerts/:alertId" element={<AlertDetailPage />} />
          <Route path="/security/alert-history" element={<AlertHistoryPage />} />
          <Route path="/security/incidents" element={<IncidentsPage />} />
          <Route path="/security/incidents/:incidentId" element={<IncidentDetailPage />} />
          <Route path="/security/response" element={<ResponseCenterPage />} />
          <Route path="/security/emergency" element={<EmergencyMonitoringPage />} />
          <Route path="/security/cameras" element={<CameraMonitoringPage />} />
          <Route path="/security/analytics" element={<IncidentAnalyticsPage />} />
          <Route path="/security/reports" element={<SecurityReportsPage />} />
          <Route path="/security/documents" element={<SafetyDocumentationPage />} />
        </Route>
        {/* ---------- Available to every signed-in role ---------- */}
        <Route element={<AuthenticatedRoute />}>
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/help" element={<HelpPage />} />
        </Route>

        {/* ---------- Catch-all ---------- */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  )
}
