from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from apps.assets.models import Asset
from apps.facilities.models import Facility, FacilityAssignment
from apps.maintenance.models import MaintenanceOrder
from apps.users.models import Permission, Role, User


class OperationsLifecycleApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        role, _ = Role.objects.get_or_create(
            name=Role.OPERATIONS_MANAGER,
            defaults={"description": "Operations manager"},
        )
        for permission_name in (
            "asset.manage",
            "workorder.create",
            "workorder.close",
            "fault.manage",
        ):
            Permission.objects.get_or_create(
                role=role,
                permission_name=permission_name,
            )
        cls.manager = User.objects.create_user(
            email="batch8-manager@example.com",
            username="batch8-manager",
            full_name="Batch 8 Manager",
            password="StrongPass123!",
            role=role,
        )
        cls.outsider = User.objects.create_user(
            email="batch8-outsider@example.com",
            username="batch8-outsider",
            full_name="Batch 8 Outsider",
            password="StrongPass123!",
            role=role,
        )
        cls.facility = Facility.objects.create(
            name="Batch 8 Facility",
            type=Facility.Type.COMMERCIAL,
            location="Cairo",
            operation_start_date=date.today(),
            created_by=cls.manager,
        )
        cls.other_facility = Facility.objects.create(
            name="Other Facility",
            type=Facility.Type.INDUSTRIAL,
            location="Giza",
            operation_start_date=date.today(),
            created_by=cls.outsider,
        )
        FacilityAssignment.objects.create(
            facility=cls.facility,
            user=cls.manager,
            role_type=FacilityAssignment.RoleType.OPERATIONS_MANAGER,
            created_by=cls.manager,
        )
        FacilityAssignment.objects.create(
            facility=cls.other_facility,
            user=cls.outsider,
            role_type=FacilityAssignment.RoleType.OPERATIONS_MANAGER,
            created_by=cls.outsider,
        )
        cls.asset = Asset.objects.create(
            facility=cls.facility,
            name="Main Pump",
            asset_type="Mechanical",
            category="pump",
            serial_number="B8-PUMP-1",
            manufacturer="Maker",
            model="P1",
            location_inside_facility="Plant room",
            installation_date=date.today(),
            operation_date=date.today(),
            created_by=cls.manager,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def create_order(self, **overrides):
        payload = {
            "asset": str(self.asset.pk),
            "asset_type": self.asset.asset_type,
            "type": "corrective",
            "priority": "high",
            "description": "Repair the leaking main pump.",
            "reason": "Seal failure",
            "expected_execution_date": date.today().isoformat(),
            "tasks": ["Isolate power", "Replace seal"],
            **overrides,
        }
        return self.client.post("/api/v1/maintenance/orders/", payload, format="json")

    def test_order_tasks_notes_completion_and_reference_are_preserved(self):
        created = self.create_order()
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["asset_type"], "Mechanical")
        self.assertTrue(created.data["reference"].startswith("WO-"))
        self.assertEqual(
            [task["label"] for task in created.data["tasks"]],
            ["Isolate power", "Replace seal"],
        )
        order_id = created.data["id"]

        notes = self.client.patch(
            f"/api/v1/maintenance/orders/{order_id}/notes/",
            {"notes": "Equipment isolated safely."},
            format="json",
        )
        self.assertEqual(notes.status_code, 200)
        self.assertEqual(notes.data["execution_notes"], "Equipment isolated safely.")
        self.assertEqual(
            self.client.post(f"/api/v1/maintenance/orders/{order_id}/start/").status_code,
            200,
        )
        blocked = self.client.post(
            f"/api/v1/maintenance/orders/{order_id}/complete/",
            {"actual_completion_date": date.today().isoformat()},
            format="json",
        )
        self.assertEqual(blocked.status_code, 409)

        for task in created.data["tasks"]:
            completed = self.client.patch(
                f"/api/v1/maintenance/orders/{order_id}/tasks/{task['id']}/",
                {"completed": True},
                format="json",
            )
            self.assertEqual(completed.status_code, 200)
        completed = self.client.post(
            f"/api/v1/maintenance/orders/{order_id}/complete/",
            {"actual_completion_date": date.today().isoformat()},
            format="json",
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.data["status"], "completed")
        closed = self.client.post(f"/api/v1/maintenance/orders/{order_id}/close/")
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.data["status"], "closed")
        self.assertEqual(closed.data["execution_notes"], "Equipment isolated safely.")
        self.assertTrue(all(task["done"] for task in closed.data["tasks"]))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.last_maintenance_date, date.today())

    def test_order_asset_type_must_match_scoped_asset(self):
        mismatch = self.create_order(asset_type="Electrical")

        self.assertEqual(mismatch.status_code, 400)
        self.assertIn("asset_type", mismatch.data["error"]["details"])
        self.assertFalse(MaintenanceOrder.objects.exists())

    def test_edit_preserves_derived_asset_type_and_asset_relationship(self):
        created = self.create_order(tasks=[])
        order_id = created.data["id"]
        edited = self.client.patch(
            f"/api/v1/maintenance/orders/{order_id}/",
            {"description": "Updated repair instructions"},
            format="json",
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.data["asset_id"], str(self.asset.pk))
        self.assertEqual(edited.data["asset_type"], self.asset.asset_type)
        replacement = Asset.objects.create(
            facility=self.facility,
            name="Replacement Pump",
            asset_type="Mechanical",
            category="pump",
            serial_number="B8-PUMP-REPLACEMENT",
            manufacturer="Maker",
            model="P3",
            location_inside_facility="Plant room",
            installation_date=date.today(),
            operation_date=date.today(),
            created_by=self.manager,
        )
        rejected = self.client.patch(
            f"/api/v1/maintenance/orders/{order_id}/",
            {"asset": str(replacement.pk)},
            format="json",
        )
        self.assertEqual(rejected.status_code, 400)

    def test_asset_search_includes_type_and_remains_facility_scoped(self):
        Asset.objects.create(
            facility=self.other_facility,
            name="Foreign Mechanical Pump",
            asset_type="Mechanical",
            category="pump",
            serial_number="B8-PUMP-FOREIGN",
            manufacturer="Maker",
            model="P2",
            location_inside_facility="Foreign plant room",
            installation_date=date.today(),
            operation_date=date.today(),
            created_by=self.outsider,
        )

        response = self.client.get("/api/v1/assets/?search=mechanical")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["id"] for row in response.data["results"]],
            [str(self.asset.pk)],
        )

    def test_cancellation_metadata_and_facility_scope_are_enforced(self):
        created = self.create_order(tasks=[])
        order_id = created.data["id"]
        cancelled = self.client.post(
            f"/api/v1/maintenance/orders/{order_id}/cancel/",
            {"reason": "Duplicate work order"},
            format="json",
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.data["status"], "cancelled")
        self.assertEqual(cancelled.data["cancellation_reason"], "Duplicate work order")
        self.assertEqual(cancelled.data["cancelled_by_id"], str(self.manager.pk))
        self.assertIsNotNone(cancelled.data["cancelled_at"])

        self.client.force_authenticate(self.outsider)
        self.assertEqual(
            self.client.get(f"/api/v1/maintenance/orders/{order_id}/").status_code,
            404,
        )
        facilities = self.client.get("/api/v1/facilities/")
        self.assertEqual([row["id"] for row in facilities.data["results"]], [str(self.other_facility.pk)])

    def test_fault_investigation_resolution_and_closure_preserve_contract(self):
        created = self.client.post(
            "/api/v1/faults/",
            {
                "asset": str(self.asset.pk),
                "fault_type": "Seal leak",
                "description": "The main pump seal is leaking.",
                "severity": "major",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.data["reference"].startswith("FLT-"))
        fault_id = created.data["id"]
        investigated = self.client.post(f"/api/v1/faults/{fault_id}/investigate/", {}, format="json")
        self.assertEqual(investigated.status_code, 200)
        self.assertEqual(investigated.data["status"], "investigating")
        resolved = self.client.post(
            f"/api/v1/faults/{fault_id}/resolve/",
            {"root_cause": "Worn seal", "resolution": "Seal replaced"},
            format="json",
        )
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(resolved.data["resolution"], "Seal replaced")
        self.assertIsNotNone(resolved.data["resolved_at"])
        closed = self.client.post(f"/api/v1/faults/{fault_id}/close/")
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.data["status"], "closed")
        self.assertEqual(closed.data["reference"], created.data["reference"])
