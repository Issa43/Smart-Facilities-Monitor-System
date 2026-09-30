from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.assets.models import Asset
from apps.audit.models import AuditLog
from apps.facilities.models import Facility, FacilityAssignment
from apps.maintenance.models import Fault
from apps.notifications.models import Notification
from apps.security.models import Camera
from apps.security.services import (
    CAMERA_MAINTENANCE_FAULT_TYPE,
    reconcile_facility_cameras,
)
from apps.users.models import Permission, Role, User


def _role(name, permissions=()):
    role, _ = Role.objects.get_or_create(name=name, defaults={"description": name})
    for permission_name in permissions:
        Permission.objects.get_or_create(role=role, permission_name=permission_name)
    return role


def _user(username, role):
    return User.objects.create_user(
        email=f"{username}@example.com",
        username=username,
        full_name=username.replace("-", " ").title(),
        password="StrongPass123!",
        role=role,
    )


class CameraMaintenanceReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        operations_role = _role(
            Role.OPERATIONS_MANAGER,
            ("asset.manage", "fault.manage", "workorder.create"),
        )
        security_role = _role(
            Role.SECURITY_OFFICER,
            ("alert.view", "incident.create", "camera.maintenance_report"),
        )
        cls.manager = _user("cam-manager", operations_role)
        cls.other_manager = _user("cam-other-manager", operations_role)
        cls.officer = _user("cam-officer", security_role)
        cls.outside_officer = _user("cam-outside-officer", security_role)
        cls.facility = Facility.objects.create(
            name="Camera Facility",
            type=Facility.Type.COMMERCIAL,
            location="Amman",
            created_by=cls.manager,
        )
        cls.other_facility = Facility.objects.create(
            name="Other Camera Facility",
            type=Facility.Type.COMMERCIAL,
            location="Irbid",
            created_by=cls.other_manager,
        )
        for facility, user, role_type in (
            (cls.facility, cls.manager, FacilityAssignment.RoleType.OPERATIONS_MANAGER),
            (cls.facility, cls.officer, FacilityAssignment.RoleType.SECURITY_OFFICER),
            (cls.other_facility, cls.other_manager, FacilityAssignment.RoleType.OPERATIONS_MANAGER),
            (cls.other_facility, cls.outside_officer, FacilityAssignment.RoleType.SECURITY_OFFICER),
        ):
            FacilityAssignment.objects.create(
                facility=facility,
                user=user,
                role_type=role_type,
                created_by=user,
            )
        result = reconcile_facility_cameras(
            facility_id=cls.facility.pk,
            required=1,
            actor=cls.manager,
        )
        cls.camera = result["created"][0]
        cls.legacy_camera = Camera.objects.create(
            facility=cls.facility,
            code="LEGACY-CAM-1",
            name="Legacy Gate Camera",
            zone="North gate",
            created_by=cls.manager,
        )

    def setUp(self):
        self.client = APIClient()

    def report(self, user, camera=None, **payload):
        self.client.force_authenticate(user)
        body = {"description": "Lens is cracked", "severity": "major"}
        body.update(payload)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                f"/api/v1/security/cameras/{(camera or self.camera).pk}/report-maintenance/",
                body,
                format="json",
            )

    def test_security_officer_creates_reported_fault(self):
        response = self.report(self.officer)

        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.data["created"])
        fault = Fault.objects.get(pk=response.data["id"])
        self.assertEqual(fault.status, Fault.Status.REPORTED)
        self.assertEqual(fault.reported_by, self.officer)
        self.assertEqual(fault.created_by, self.officer)
        self.assertEqual(fault.asset_id, self.camera.asset_id)
        self.assertEqual(fault.fault_type, CAMERA_MAINTENANCE_FAULT_TYPE)
        self.assertEqual(fault.severity, Fault.Severity.MAJOR)
        self.assertEqual(response.data["reference"], fault.reference)
        self.assertEqual(response.data["camera_id"], str(self.camera.pk))
        self.assertNotIn("assigned_engineer_id", response.data)
        self.assertTrue(
            AuditLog.objects.filter(
                action="camera.maintenance_reported",
                entity_id=str(fault.pk),
            ).exists()
        )

    def test_severity_defaults_to_moderate_and_is_validated(self):
        self.client.force_authenticate(self.officer)
        url = f"/api/v1/security/cameras/{self.camera.pk}/report-maintenance/"

        invalid = self.client.post(url, {"description": "x", "severity": "catastrophic"}, format="json")
        blank = self.client.post(url, {"description": "  "}, format="json")
        with self.captureOnCommitCallbacks(execute=True):
            default = self.client.post(url, {"description": "Blurry image"}, format="json")

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(blank.status_code, 400)
        self.assertEqual(default.status_code, 201)
        self.assertEqual(default.data["severity"], Fault.Severity.MODERATE)

    def test_duplicate_report_returns_the_open_fault(self):
        first = self.report(self.officer)
        second = self.report(self.officer, description="Still broken")

        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.data["created"])
        self.assertEqual(second.data["id"], first.data["id"])
        self.assertEqual(
            Fault.objects.filter(
                asset_id=self.camera.asset_id,
                fault_type=CAMERA_MAINTENANCE_FAULT_TYPE,
            ).count(),
            1,
        )

    def test_investigating_fault_is_still_reused_but_closed_fault_is_not(self):
        first = self.report(self.officer)
        Fault.objects.filter(pk=first.data["id"]).update(status=Fault.Status.INVESTIGATING)
        self.assertEqual(self.report(self.officer).data["id"], first.data["id"])

        Fault.objects.filter(pk=first.data["id"]).update(
            status=Fault.Status.CLOSED,
            root_cause="Impact",
            resolution="Lens replaced",
            resolved_at="2026-01-01T00:00:00Z",
        )
        again = self.report(self.officer)

        self.assertEqual(again.status_code, 201)
        self.assertNotEqual(again.data["id"], first.data["id"])

    def test_camera_without_asset_gets_one_before_the_fault(self):
        self.assertIsNone(self.legacy_camera.asset_id)

        response = self.report(self.officer, camera=self.legacy_camera)

        self.assertEqual(response.status_code, 201, response.content)
        self.legacy_camera.refresh_from_db()
        asset = self.legacy_camera.asset
        self.assertIsNotNone(asset)
        self.assertEqual(asset.facility_id, self.facility.pk)
        self.assertEqual(asset.serial_number, "LEGACY-CAM-1")
        self.assertEqual(asset.location_inside_facility, "North gate")
        self.assertEqual(asset.asset_type, "camera")
        self.legacy_camera.full_clean()
        self.assertEqual(Fault.objects.get(pk=response.data["id"]).asset, asset)

    def test_out_of_scope_camera_is_not_found(self):
        response = self.report(self.outside_officer)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Fault.objects.exists())

    def test_operations_manager_cannot_use_security_endpoint(self):
        response = self.report(self.manager)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Fault.objects.exists())

    def test_permission_is_required(self):
        Permission.objects.filter(
            role__name=Role.SECURITY_OFFICER,
            permission_name="camera.maintenance_report",
        ).delete()

        response = self.report(self.officer)

        self.assertEqual(response.status_code, 403)
        self.client.force_authenticate(self.officer)
        self.assertEqual(self.client.get("/api/v1/security/cameras/").status_code, 200)

    def test_security_officer_cannot_drive_the_fault_workflow(self):
        fault_id = self.report(self.officer).data["id"]
        self.client.force_authenticate(self.officer)

        for path, body in (
            ("investigate", {}),
            ("resolve", {"root_cause": "x", "resolution": "y"}),
            ("close", {}),
        ):
            response = self.client.post(
                f"/api/v1/faults/{fault_id}/{path}/", body, format="json"
            )
            self.assertEqual(response.status_code, 403, path)
        self.assertEqual(
            self.client.post(
                "/api/v1/maintenance/orders/",
                {"asset": str(self.camera.asset_id), "title": "x"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(Fault.objects.get(pk=fault_id).status, Fault.Status.REPORTED)

    def test_operations_manager_takes_over_with_existing_workflow(self):
        fault_id = self.report(self.officer).data["id"]
        self.client.force_authenticate(self.manager)

        listed = self.client.get("/api/v1/faults/", {"asset": str(self.camera.asset_id)})
        investigate = self.client.post(f"/api/v1/faults/{fault_id}/investigate/", {}, format="json")

        rows = listed.data.get("results", listed.data)
        self.assertEqual([row["id"] for row in rows], [fault_id])
        self.assertEqual(investigate.status_code, 200, investigate.content)
        self.assertEqual(investigate.data["status"], Fault.Status.INVESTIGATING)

    def test_full_chain_through_existing_order_and_task_workflow(self):
        Permission.objects.get_or_create(
            role=self.manager.role, permission_name="workorder.close"
        )
        fault_id = self.report(self.officer).data["id"]
        asset_id = str(self.camera.asset_id)
        self.client.force_authenticate(self.manager)

        order = self.client.post(
            "/api/v1/maintenance/orders/",
            {
                "asset": asset_id,
                "type": "corrective",
                "priority": "high",
                "description": "Replace the cracked lens",
                "reason": f"Camera fault {fault_id}",
                "assigned_to": str(self.manager.pk),
                "expected_execution_date": "2026-10-01",
                "tasks": ["Replace lens"],
            },
            format="json",
        )
        self.assertEqual(order.status_code, 201, order.content)
        order_id = order.data["id"]
        task_id = order.data["tasks"][0]["id"]

        started = self.client.post(f"/api/v1/maintenance/orders/{order_id}/start/", {}, format="json")
        self.assertEqual(started.status_code, 200, started.content)
        self.assertEqual(
            Asset.objects.get(pk=asset_id).current_status, Asset.Status.UNDER_MAINTENANCE
        )
        task = self.client.patch(
            f"/api/v1/maintenance/orders/{order_id}/tasks/{task_id}/",
            {"completed": True},
            format="json",
        )
        self.assertEqual(task.status_code, 200, task.content)
        for path, body in (
            ("complete", {"actual_completion_date": timezone.localdate().isoformat()}),
            ("close", {}),
        ):
            response = self.client.post(
                f"/api/v1/maintenance/orders/{order_id}/{path}/", body, format="json"
            )
            self.assertEqual(response.status_code, 200, (path, response.content))
        for path, body in (
            ("investigate", {}),
            ("resolve", {"root_cause": "Impact damage", "resolution": "Lens replaced"}),
            ("close", {}),
        ):
            response = self.client.post(f"/api/v1/faults/{fault_id}/{path}/", body, format="json")
            self.assertEqual(response.status_code, 200, (path, response.content))

        self.assertEqual(Fault.objects.get(pk=fault_id).status, Fault.Status.CLOSED)
        self.assertEqual(
            Asset.objects.get(pk=asset_id).current_status, Asset.Status.OPERATIONAL
        )
        self.camera.refresh_from_db()
        self.assertTrue(self.camera.is_active)
        self.assertEqual(str(self.camera.asset_id), asset_id)
        # Once closed, a new problem on the same camera is a new report.
        self.assertEqual(self.report(self.officer).status_code, 201)

    def test_assigned_operations_managers_are_notified_once(self):
        self.report(self.officer)
        self.report(self.officer)

        notifications = Notification.objects.filter(category=Notification.Category.MAINTENANCE)
        self.assertEqual(
            list(notifications.values_list("recipient_id", flat=True)),
            [self.manager.pk],
        )
        notification = notifications.get()
        self.assertEqual(notification.href, "/operations/faults")
        self.assertIn(self.camera.code, notification.body)
        self.assertFalse(
            Notification.objects.filter(recipient=self.other_manager).exists()
        )
        self.assertFalse(Notification.objects.filter(recipient=self.officer).exists())

    def test_reporting_does_not_change_asset_or_camera_state(self):
        self.report(self.officer)

        self.camera.refresh_from_db()
        self.assertEqual(self.camera.status, Camera.Status.OFFLINE)
        self.assertEqual(
            Asset.objects.get(pk=self.camera.asset_id).current_status,
            Asset.Status.OPERATIONAL,
        )
