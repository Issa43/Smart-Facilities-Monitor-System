from datetime import date, timedelta
from decimal import Decimal
from threading import Barrier, Lock, Thread

from django.core.exceptions import ValidationError
from django.db import OperationalError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from apps.materials.models import Material, MaterialConsumptionRecord, MaterialRequest
from apps.materials.services import consume_material
from apps.notifications.models import Notification
from apps.projects.models import Project, ProjectAssignment
from apps.users.models import Permission, Role, User


class MaterialWorkflowMixin:
    @classmethod
    def create_users(cls):
        cls.admin_role, _ = Role.objects.get_or_create(
            name=Role.SUPER_ADMIN, defaults={"description": "Admin"}
        )
        cls.manager_role, _ = Role.objects.get_or_create(
            name=Role.CONSTRUCTION_MANAGER, defaults={"description": "Manager"}
        )
        for permission_name in ("material.manage", "material.request", "material.stock"):
            Permission.objects.get_or_create(
                role=cls.manager_role, permission_name=permission_name
            )
        cls.admin = User.objects.create_user(
            email="batch6-admin@example.com",
            username="batch6-admin",
            full_name="Batch 6 Admin",
            password="StrongPass123!",
            role=cls.admin_role,
        )
        cls.manager = User.objects.create_user(
            email="batch6-manager@example.com",
            username="batch6-manager",
            full_name="Batch 6 Manager",
            password="StrongPass123!",
            role=cls.manager_role,
        )

    @classmethod
    def create_project(cls):
        today = date.today()
        cls.project = Project.objects.create(
            name="Batch 6 Project",
            facility_type=Project.FacilityType.COMMERCIAL,
            location="Cairo",
            start_date=today,
            expected_completion_date=today + timedelta(days=30),
            status=Project.Status.IN_PROGRESS,
            created_by=cls.admin,
        )
        ProjectAssignment.objects.create(
            project=cls.project,
            user=cls.manager,
            role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
            created_by=cls.admin,
        )

    @classmethod
    def create_material(cls, **overrides):
        values = {
            "project": cls.project,
            "name": "Cement",
            "unit": Material.Unit.BAG,
            "quantity_required": Decimal("10.000"),
            "quantity_used": Decimal("0.000"),
            "quantity_remaining": Decimal("10.000"),
            "min_stock_threshold": Decimal("4.000"),
            "created_by": cls.manager,
        }
        values.update(overrides)
        return Material.objects.create(**values)


class MaterialWorkflowApiTests(MaterialWorkflowMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_users()
        cls.create_project()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def test_material_crud_cannot_forge_consumed_or_remaining_stock(self):
        response = self.client.post(
            "/api/v1/construction/materials/",
            {
                "project": str(self.project.id),
                "name": "Steel",
                "unit": Material.Unit.TONNE,
                "quantity_required": "12.000",
                "quantity_used": "7.000",
                "quantity_remaining": "5.000",
                "min_stock_threshold": "2.000",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Decimal(response.data["quantity_used"]), Decimal("0.000"))
        self.assertEqual(Decimal(response.data["quantity_remaining"]), Decimal("12.000"))

        material = Material.objects.get(pk=response.data["id"])
        response = self.client.patch(
            f"/api/v1/construction/materials/{material.id}/",
            {"quantity_used": "9.000", "quantity_required": "15.000"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        material.refresh_from_db()
        self.assertEqual(material.quantity_used, Decimal("0.000"))
        self.assertEqual(material.quantity_remaining, Decimal("15.000"))

    def test_unit_priority_uuid_scope_and_self_approval_are_enforced(self):
        invalid_unit = self.client.post(
            "/api/v1/construction/materials/",
            {
                "project": str(self.project.id),
                "name": "Invalid unit",
                "unit": "cubic-feet",
                "quantity_required": "1.000",
                "min_stock_threshold": "0.000",
            },
            format="json",
        )
        self.assertEqual(invalid_unit.status_code, 400)

        material = self.create_material()
        request = self.client.post(
            "/api/v1/construction/material-requests/",
            {
                "project": str(self.project.id),
                "material": str(material.id),
                "quantity_requested": "3.000",
                "reason": "Required for the next work package.",
                "priority": MaterialRequest.Priority.URGENT,
            },
            format="json",
        )
        self.assertEqual(request.status_code, 201)
        self.assertEqual(request.data["priority"], MaterialRequest.Priority.URGENT)

        approval = self.client.post(
            f"/api/v1/construction/material-requests/{request.data['id']}/approve/"
        )
        self.assertEqual(approval.status_code, 403)
        request_obj = MaterialRequest.objects.get(pk=request.data["id"])
        self.assertEqual(request_obj.status, MaterialRequest.Status.SUBMITTED)

    def test_consumption_is_immutable_protected_and_notifies_once_on_threshold_crossing(self):
        material = self.create_material()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/api/v1/construction/materials/{material.id}/consumption/",
                {"quantity": "6.000"},
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        material.refresh_from_db()
        self.assertEqual(material.quantity_remaining, Decimal("4.000"))
        notification = Notification.objects.get(recipient=self.manager)
        self.assertEqual(
            notification.href,
            f"/construction/materials?material={material.id}",
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/api/v1/construction/materials/{material.id}/consumption/",
                {"quantity": "1.000"},
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Notification.objects.filter(recipient=self.manager).count(), 1)

        record = MaterialConsumptionRecord.objects.filter(material=material).first()
        record.quantity_used = Decimal("2.000")
        with self.assertRaises(ValidationError):
            record.save()

        delete = self.client.delete(f"/api/v1/construction/materials/{material.id}/")
        self.assertEqual(delete.status_code, 409)

    def test_material_request_cannot_relink_to_material_outside_project_scope(self):
        material = self.create_material()
        request = MaterialRequest.objects.create(
            project=self.project,
            material=material,
            quantity_requested=Decimal("2.000"),
            reason="Required for the assigned project.",
            created_by=self.manager,
        )
        today = date.today()
        outside_project = Project.objects.create(
            name="Outside material project",
            facility_type=Project.FacilityType.COMMERCIAL,
            location="Alexandria",
            start_date=today,
            expected_completion_date=today + timedelta(days=30),
            status=Project.Status.IN_PROGRESS,
            created_by=self.admin,
        )
        outside_material = Material.objects.create(
            project=outside_project,
            name="Outside steel",
            unit=Material.Unit.TONNE,
            quantity_required=Decimal("5.000"),
            quantity_used=Decimal("0.000"),
            quantity_remaining=Decimal("5.000"),
            min_stock_threshold=Decimal("1.000"),
            created_by=self.admin,
        )

        response = self.client.patch(
            f"/api/v1/construction/material-requests/{request.id}/",
            {"material": str(outside_material.id)},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        request.refresh_from_db()
        self.assertEqual(request.material_id, material.id)


class MaterialConsumptionConcurrencyTests(MaterialWorkflowMixin, TransactionTestCase):
    reset_sequences = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.create_users()
        cls.create_project()

    def setUp(self):
        self.material = self.create_material()

    def test_simultaneous_consumption_cannot_overdraw_stock(self):
        barrier = Barrier(2)
        result_lock = Lock()
        results = []

        def consume():
            close_old_connections()
            try:
                actor = User.objects.get(pk=self.manager.pk)
                barrier.wait(timeout=5)
                consume_material(
                    material_id=self.material.pk,
                    quantity="6.000",
                    actor=actor,
                )
                result = "consumed"
            except ValidationError:
                result = "rejected"
            except OperationalError:
                # SQLite's test backend has no row-level SELECT FOR UPDATE and
                # reports the competing write as table lock contention. This
                # is the equivalent safe outcome: the second write is refused.
                result = "contended"
            finally:
                close_old_connections()
            with result_lock:
                results.append(result)

        threads = [Thread(target=consume), Thread(target=consume)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(len(results), 2)
        consumed_count = results.count("consumed")
        if connection.vendor == "sqlite" and consumed_count == 0:
            # SQLite has no row-level SELECT FOR UPDATE. Under unlucky timing
            # it can reject both concurrent writers at the table-lock layer;
            # the safety invariant is still that neither write overdraws.
            self.assertEqual(results.count("contended"), 2)
            expected_used = Decimal("0.000")
            expected_remaining = Decimal("10.000")
            expected_records = 0
        else:
            self.assertEqual(consumed_count, 1)
            self.assertIn(
                next(result for result in results if result != "consumed"),
                {"rejected", "contended"},
            )
            expected_used = Decimal("6.000")
            expected_remaining = Decimal("4.000")
            expected_records = 1
        self.material.refresh_from_db()
        self.assertEqual(self.material.quantity_used, expected_used)
        self.assertEqual(self.material.quantity_remaining, expected_remaining)
        self.assertEqual(
            MaterialConsumptionRecord.objects.filter(material=self.material).count(),
            expected_records,
        )
