import threading
from unittest import mock, skipUnless

from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.db.models.query import QuerySet
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from apps.assets.models import Asset
from apps.audit.models import AuditLog
from apps.facilities.models import Facility, FacilityAssignment
from apps.security.models import Camera
from apps.security.services import reconcile_facility_cameras
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


def _facility(name, creator, **overrides):
    return Facility.objects.create(
        name=name,
        type=Facility.Type.COMMERCIAL,
        location="Amman",
        created_by=creator,
        **overrides,
    )


def _manual_camera(facility, code, creator):
    return Camera.objects.create(
        facility=facility,
        code=code,
        name=code,
        zone="Lobby",
        created_by=creator,
    )


class CameraProvisioningServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = _user("prov-manager", _role(Role.OPERATIONS_MANAGER, ("asset.manage",)))
        cls.facility = _facility("Provisioned Facility", cls.manager)

    def reconcile(self, required):
        return reconcile_facility_cameras(
            facility_id=self.facility.pk,
            required=required,
            actor=self.manager,
        )

    def active_cameras(self):
        return Camera.objects.filter(facility=self.facility)

    def test_zero_to_five_creates_five_paired_cameras(self):
        result = self.reconcile(5)

        self.assertEqual(result["existing"], 0)
        self.assertEqual(len(result["created"]), 5)
        self.assertEqual(result["surplus"], 0)
        self.assertEqual(self.active_cameras().count(), 5)
        self.facility.refresh_from_db()
        self.assertEqual(self.facility.required_camera_count, 5)
        prefix = f"CAM-{self.facility.pk.hex[:12].upper()}-"
        codes = sorted(self.active_cameras().values_list("code", flat=True))
        self.assertEqual(codes, [f"{prefix}{n:03d}" for n in range(1, 6)])
        for camera in self.active_cameras().select_related("asset"):
            camera.full_clean()
            self.assertIsNotNone(camera.asset)
            self.assertEqual(camera.asset.facility_id, self.facility.pk)
            self.assertEqual(camera.asset.serial_number, camera.code)
            self.assertEqual(camera.asset.asset_type, "camera")
            self.assertEqual(camera.asset.category, "security")
            self.assertEqual(camera.status, Camera.Status.OFFLINE)

    def test_three_existing_to_five_creates_two(self):
        for n in range(3):
            _manual_camera(self.facility, f"MANUAL-{n}", self.manager)

        manual_asset = Asset.objects.create(
            facility=self.facility,
            name="Legacy lobby camera",
            asset_type="CCTV",
            category="security",
            serial_number="LEGACY-ASSET-1",
            manufacturer="Axis",
            model="P3245",
            location_inside_facility="Lobby",
            installation_date="2025-01-01",
            created_by=self.manager,
        )
        Camera.objects.filter(code="MANUAL-0").update(asset=manual_asset)
        manual_before = list(
            Camera.objects.filter(code__startswith="MANUAL-").order_by("code").values()
        )

        result = self.reconcile(5)

        self.assertEqual(result["existing"], 3)
        self.assertEqual(len(result["created"]), 2)
        self.assertEqual(self.active_cameras().count(), 5)
        self.assertEqual(Asset.objects.filter(facility=self.facility).count(), 3)
        # Pre-existing cameras and their Asset are left exactly as they were.
        self.assertEqual(
            list(Camera.objects.filter(code__startswith="MANUAL-").order_by("code").values()),
            manual_before,
        )
        manual_asset_after = Asset.objects.get(pk=manual_asset.pk)
        self.assertEqual(
            (manual_asset_after.name, manual_asset_after.asset_type, manual_asset_after.model),
            ("Legacy lobby camera", "CCTV", "P3245"),
        )

    def test_zero_required_keeps_existing_cameras(self):
        self.reconcile(4)
        ids_before = set(self.active_cameras().values_list("pk", flat=True))

        result = self.reconcile(0)

        self.assertEqual(result["created"], [])
        self.assertEqual(result["surplus"], 4)
        self.assertEqual(set(self.active_cameras().values_list("pk", flat=True)), ids_before)
        self.assertEqual(Asset.objects.filter(facility=self.facility).count(), 4)
        self.facility.refresh_from_db()
        self.assertEqual(self.facility.required_camera_count, 0)

    def test_five_to_five_and_repeated_requests_create_nothing(self):
        self.reconcile(5)
        audit_count = AuditLog.objects.filter(action="facility.cameras_reconciled").count()

        for _ in range(3):
            result = self.reconcile(5)
            self.assertEqual(result["existing"], 5)
            self.assertEqual(result["created"], [])
            self.assertEqual(result["surplus"], 0)

        self.assertEqual(self.active_cameras().count(), 5)
        self.assertEqual(Asset.objects.filter(facility=self.facility).count(), 5)
        self.assertEqual(
            AuditLog.objects.filter(action="facility.cameras_reconciled").count(),
            audit_count,
        )

    def test_lowering_the_requirement_reports_surplus_and_deletes_nothing(self):
        self.reconcile(5)
        camera = self.active_cameras().first()

        result = self.reconcile(3)

        self.assertEqual(result["existing"], 5)
        self.assertEqual(result["created"], [])
        self.assertEqual(result["surplus"], 2)
        self.assertEqual(self.active_cameras().count(), 5)
        self.assertEqual(Camera.all_objects.filter(facility=self.facility).count(), 5)
        camera.refresh_from_db()
        self.assertTrue(camera.is_active)
        self.facility.refresh_from_db()
        self.assertEqual(self.facility.required_camera_count, 3)

    def test_numbering_skips_soft_deleted_camera_codes(self):
        self.reconcile(2)
        self.active_cameras().order_by("code").last().soft_delete()

        result = self.reconcile(2)

        prefix = f"CAM-{self.facility.pk.hex[:12].upper()}-"
        self.assertEqual([camera.code for camera in result["created"]], [f"{prefix}003"])
        self.assertEqual(
            Camera.all_objects.filter(facility=self.facility).count(),
            3,
        )

    def test_failure_mid_reconciliation_rolls_everything_back(self):
        original_save = Camera.save
        calls = {"count": 0}

        def failing_save(camera, *args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 4:
                raise RuntimeError("camera #4 failed")
            return original_save(camera, *args, **kwargs)

        with mock.patch.object(Camera, "save", autospec=True, side_effect=failing_save):
            with self.assertRaises(RuntimeError):
                self.reconcile(5)

        self.assertEqual(Camera.all_objects.filter(facility=self.facility).count(), 0)
        self.assertEqual(Asset.all_objects.filter(facility=self.facility).count(), 0)
        self.facility.refresh_from_db()
        self.assertIsNone(self.facility.required_camera_count)
        self.assertFalse(
            AuditLog.objects.filter(action="facility.cameras_reconciled").exists()
        )

    def test_facility_row_is_locked_before_counting(self):
        original = QuerySet.select_for_update
        locked_models = []

        def spy(queryset, *args, **kwargs):
            locked_models.append(queryset.model)
            return original(queryset, *args, **kwargs)

        with mock.patch.object(QuerySet, "select_for_update", autospec=True, side_effect=spy):
            self.reconcile(1)

        self.assertEqual(locked_models[0], Facility)

    def test_decommissioned_facility_is_rejected(self):
        facility = _facility(
            "Closed Facility",
            self.manager,
            status=Facility.Status.DECOMMISSIONED,
        )
        with self.assertRaises(ValidationError):
            reconcile_facility_cameras(facility_id=facility.pk, required=2, actor=self.manager)
        self.assertFalse(Camera.objects.filter(facility=facility).exists())

    def test_out_of_range_counts_are_rejected(self):
        for value in (-1, 201, True, "5"):
            with self.assertRaises(ValidationError):
                self.reconcile(value)

    def test_reconciliation_is_audited(self):
        _manual_camera(self.facility, "MANUAL-A", self.manager)

        self.reconcile(3)

        log = AuditLog.objects.get(action="facility.cameras_reconciled")
        self.assertEqual(log.actor, self.manager)
        self.assertEqual(log.entity_id, str(self.facility.pk))
        self.assertEqual(
            log.before,
            {"required_camera_count": None, "active_camera_count": 1},
        )
        self.assertEqual(
            log.after,
            {
                "required_camera_count": 3,
                "active_camera_count": 3,
                "created_count": 2,
                "surplus_count": 0,
            },
        )


class CameraRequirementApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        operations_role = _role(Role.OPERATIONS_MANAGER, ("asset.manage",))
        security_role = _role(Role.SECURITY_OFFICER, ("alert.view", "camera.maintenance_report"))
        cls.manager = _user("req-manager", operations_role)
        cls.outsider = _user("req-outsider", operations_role)
        cls.security = _user("req-security", security_role)
        cls.super_admin = _user("req-super", _role(Role.SUPER_ADMIN))
        cls.facility = _facility("Requirement Facility", cls.manager)
        cls.other_facility = _facility("Other Requirement Facility", cls.outsider)
        for facility, user, role_type in (
            (cls.facility, cls.manager, FacilityAssignment.RoleType.OPERATIONS_MANAGER),
            (cls.other_facility, cls.outsider, FacilityAssignment.RoleType.OPERATIONS_MANAGER),
            (cls.facility, cls.security, FacilityAssignment.RoleType.SECURITY_OFFICER),
        ):
            FacilityAssignment.objects.create(
                facility=facility,
                user=user,
                role_type=role_type,
                created_by=user,
            )

    def setUp(self):
        self.client = APIClient()

    def url(self, facility=None):
        return f"/api/v1/facilities/{(facility or self.facility).pk}/camera-requirement/"

    def put(self, user, count, facility=None):
        self.client.force_authenticate(user)
        return self.client.put(
            self.url(facility),
            {"required_camera_count": count},
            format="json",
        )

    def test_operations_manager_sets_count_and_repeats_are_idempotent(self):
        first = self.put(self.manager, 5)
        second = self.put(self.manager, 5)

        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.data["required_camera_count"], 5)
        self.assertEqual(first.data["existing"], 0)
        self.assertEqual(first.data["created"], 5)
        self.assertEqual(first.data["surplus"], 0)
        self.assertEqual(len(first.data["cameras"]), 5)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["existing"], 5)
        self.assertEqual(second.data["created"], 0)
        self.assertEqual(Camera.objects.filter(facility=self.facility).count(), 5)

    def test_lowering_reports_surplus(self):
        self.put(self.manager, 5)

        response = self.put(self.manager, 3)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["surplus"], 2)
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(len(response.data["cameras"]), 5)

    def test_get_returns_current_state_without_changes(self):
        self.put(self.manager, 2)
        self.client.force_authenticate(self.manager)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["required_camera_count"], 2)
        self.assertEqual(response.data["camera_count"], 2)
        self.assertEqual(response.data["created"], 0)

    def test_facility_serializer_exposes_requirement_and_camera_count(self):
        self.put(self.manager, 2)
        self.client.force_authenticate(self.manager)

        detail = self.client.get(f"/api/v1/facilities/{self.facility.pk}/")
        listing = self.client.get("/api/v1/facilities/")

        self.assertEqual(detail.data["required_camera_count"], 2)
        self.assertEqual(detail.data["camera_count"], 2)
        self.assertIn("asset_count", detail.data)
        rows = listing.data.get("results", listing.data)
        self.assertEqual(rows[0]["camera_count"], 2)

    def test_operations_manager_cannot_touch_unassigned_facility(self):
        response = self.put(self.manager, 3, facility=self.other_facility)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Camera.objects.filter(facility=self.other_facility).exists())

    def test_super_admin_can_set_any_facility(self):
        response = self.put(self.super_admin, 1, facility=self.other_facility)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["created"], 1)

    def test_security_officer_is_forbidden(self):
        response = self.put(self.security, 3)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Camera.objects.filter(facility=self.facility).exists())

    def test_invalid_counts_return_400(self):
        for value in (-1, 201, "many", None):
            response = self.put(self.manager, value)
            self.assertEqual(response.status_code, 400, value)

    def test_decommissioned_facility_returns_conflict(self):
        Facility.objects.filter(pk=self.facility.pk).update(
            status=Facility.Status.DECOMMISSIONED
        )

        response = self.put(self.manager, 2)

        self.assertEqual(response.status_code, 409)


@skipUnless(connection.vendor == "postgresql", "Row locks need PostgreSQL")
class ConcurrentCameraProvisioningTests(TransactionTestCase):
    def test_concurrent_requests_never_exceed_the_required_count(self):
        manager = _user("concurrent-manager", _role(Role.OPERATIONS_MANAGER))
        facility = _facility("Concurrent Facility", manager)
        barrier = threading.Barrier(4)
        errors = []

        def worker():
            try:
                barrier.wait()
                reconcile_facility_cameras(facility_id=facility.pk, required=5, actor=manager)
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(Camera.objects.filter(facility=facility).count(), 5)
        self.assertEqual(Asset.objects.filter(facility=facility).count(), 5)
