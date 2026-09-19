from datetime import date, timedelta

from django.test import TestCase
from rest_framework.test import APIClient

from apps.assets.models import Asset
from apps.audit.models import AuditLog
from apps.facilities.models import Facility, FacilityAssignment
from apps.users.models import Permission, Role, User


class AssetApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operations_role, _ = Role.objects.get_or_create(
            name=Role.OPERATIONS_MANAGER,
            defaults={"description": "Operations manager"},
        )
        for name in ("asset.manage", "asset.status", "workorder.create"):
            Permission.objects.get_or_create(
                role=cls.operations_role,
                permission_name=name,
            )
        cls.construction_role, _ = Role.objects.get_or_create(
            name=Role.CONSTRUCTION_MANAGER,
            defaults={"description": "Construction manager"},
        )
        cls.security_role, _ = Role.objects.get_or_create(
            name=Role.SECURITY_OFFICER,
            defaults={"description": "Security officer"},
        )
        cls.super_role, _ = Role.objects.get_or_create(
            name=Role.SUPER_ADMIN,
            defaults={"description": "Super admin"},
        )
        cls.manager = cls._user("asset-manager", cls.operations_role)
        cls.outsider = cls._user("asset-outsider", cls.operations_role)
        cls.construction = cls._user("asset-construction", cls.construction_role)
        cls.security = cls._user("asset-security", cls.security_role)
        cls.super_admin = cls._user("asset-super", cls.super_role)
        cls.facility = cls._facility("Scoped Facility", cls.manager)
        cls.other_facility = cls._facility("Other Facility", cls.outsider)
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
        cls.asset = cls._asset(
            facility=cls.facility,
            creator=cls.manager,
            serial="ASSET-SCOPED-1",
            name="Main Chiller",
            asset_type="Chiller",
            category="hvac-custom",
            manufacturer="Carrier",
            location="Roof plant room",
        )
        cls.other_asset = cls._asset(
            facility=cls.other_facility,
            creator=cls.outsider,
            serial="ASSET-OTHER-1",
            name="Foreign Pump",
            asset_type="Pump",
            category="mechanical",
            manufacturer="Grundfos",
            location="Basement",
        )

    @staticmethod
    def _user(username, role):
        return User.objects.create_user(
            email=f"{username}@example.com",
            username=username,
            full_name=username.replace("-", " ").title(),
            password="StrongPass123!",
            role=role,
        )

    @staticmethod
    def _facility(name, creator):
        return Facility.objects.create(
            name=name,
            type=Facility.Type.COMMERCIAL,
            location="Cairo",
            operation_start_date=date.today(),
            created_by=creator,
        )

    @staticmethod
    def _asset(*, facility, creator, serial, name, asset_type, category, manufacturer, location):
        return Asset.objects.create(
            facility=facility,
            name=name,
            asset_type=asset_type,
            category=category,
            serial_number=serial,
            manufacturer=manufacturer,
            model="M-1",
            location_inside_facility=location,
            installation_date=date.today() - timedelta(days=30),
            operation_date=date.today() - timedelta(days=20),
            created_by=creator,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def payload(self, **overrides):
        values = {
            "facility": str(self.facility.pk),
            "name": "Emergency Generator",
            "asset_type": "Generator",
            "category": "power-generation",
            "serial_number": "ASSET-NEW-1",
            "manufacturer": "Caterpillar",
            "model": "CAT-500",
            "location_inside_facility": "Service yard",
            "installation_date": (date.today() - timedelta(days=10)).isoformat(),
            "operation_date": (date.today() - timedelta(days=5)).isoformat(),
            "notes": "Critical backup asset",
        }
        values.update(overrides)
        return values

    def test_create_read_update_and_archive_are_persistent_and_audited(self):
        created = self.client.post("/api/v1/assets/", self.payload(), format="json")
        self.assertEqual(created.status_code, 201)
        asset_id = created.data["id"]
        self.assertEqual(created.data["asset_type"], "Generator")
        self.assertEqual(created.data["category"], "power-generation")
        self.assertEqual(created.data["current_status"], Asset.Status.OPERATIONAL)
        self.assertTrue(Asset.objects.filter(pk=asset_id, notes="Critical backup asset").exists())

        updated = self.client.patch(
            f"/api/v1/assets/{asset_id}/",
            {"asset_type": "Diesel Generator", "model": "CAT-600"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["asset_type"], "Diesel Generator")
        self.assertEqual(self.client.get(f"/api/v1/assets/{asset_id}/").data["model"], "CAT-600")

        archived = self.client.delete(f"/api/v1/assets/{asset_id}/")
        self.assertEqual(archived.status_code, 204)
        self.assertFalse(Asset.all_objects.get(pk=asset_id).is_active)
        actions = set(
            AuditLog.objects.filter(entity_id=str(asset_id)).values_list("action", flat=True)
        )
        self.assertTrue(
            {"asset.created", "asset.updated", "asset.archived"}.issubset(actions)
        )

    def test_asset_create_keeps_semantic_and_generic_audit_records(self):
        with self.captureOnCommitCallbacks(execute=True):
            created = self.client.post(
                "/api/v1/assets/",
                self.payload(serial_number="ASSET-AUDIT-PAIR"),
                format="json",
            )

        self.assertEqual(created.status_code, 201)
        asset_id = created.data["id"]
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.manager,
                action="asset.created",
                entity_type="assets.asset",
                entity_id=str(asset_id),
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.manager,
                action="api.post",
                entity_type="api_endpoint",
                entity_ref="/api/v1/assets/",
            ).exists()
        )

    def test_duplicate_serial_returns_validation_error_without_duplicate(self):
        response = self.client.post(
            "/api/v1/assets/",
            self.payload(serial_number=self.asset.serial_number),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("serial_number", response.data["error"]["details"])
        self.assertEqual(Asset.all_objects.filter(serial_number=self.asset.serial_number).count(), 1)

    def test_validation_rejects_inactive_or_foreign_facility_and_invalid_dates(self):
        foreign = self.client.post(
            "/api/v1/assets/",
            self.payload(facility=str(self.other_facility.pk)),
            format="json",
        )
        self.assertEqual(foreign.status_code, 400)
        invalid_dates = self.client.post(
            "/api/v1/assets/",
            self.payload(
                installation_date=date.today().isoformat(),
                operation_date=(date.today() - timedelta(days=1)).isoformat(),
            ),
            format="json",
        )
        self.assertEqual(invalid_dates.status_code, 400)

    def test_facility_is_immutable(self):
        response = self.client.patch(
            f"/api/v1/assets/{self.asset.pk}/",
            {"facility": str(self.other_facility.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.facility_id, self.facility.pk)

    def test_search_filters_ordering_and_real_filter_options_are_scoped(self):
        searched = self.client.get("/api/v1/assets/?search=roof")
        self.assertEqual([row["id"] for row in searched.data["results"]], [str(self.asset.pk)])
        filtered = self.client.get(
            "/api/v1/assets/?asset_type=Chiller&current_status=operational&manufacturer=Carrier"
        )
        self.assertEqual([row["id"] for row in filtered.data["results"]], [str(self.asset.pk)])
        options = self.client.get("/api/v1/assets/filter-options/")
        self.assertEqual(options.status_code, 200)
        self.assertEqual(options.data["asset_types"], ["Chiller"])
        self.assertEqual(options.data["categories"], ["hvac-custom"])
        self.assertEqual(options.data["manufacturers"], ["Carrier"])

    def test_idor_is_hidden_for_every_asset_mutation(self):
        asset_url = f"/api/v1/assets/{self.other_asset.pk}/"
        self.assertEqual(self.client.get(asset_url).status_code, 404)
        self.assertEqual(self.client.patch(asset_url, {"name": "Leaked"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(asset_url).status_code, 404)
        self.assertEqual(
            self.client.post(
                f"{asset_url}transition-status/",
                {"target_status": "under_maintenance"},
                format="json",
            ).status_code,
            404,
        )
        related = self.client.post(
            "/api/v1/maintenance/orders/",
            {
                "asset": str(self.other_asset.pk),
                "asset_type": self.other_asset.asset_type,
                "type": "corrective",
                "priority": "high",
                "description": "Unauthorized cross-facility request",
                "reason": "IDOR probe",
                "expected_execution_date": date.today().isoformat(),
            },
            format="json",
        )
        self.assertEqual(related.status_code, 400)
        self.assertIn("asset", related.data["error"]["details"])

    def test_lifecycle_allows_only_the_backend_state_machine_and_is_audited(self):
        changed = self.client.post(
            f"/api/v1/assets/{self.asset.pk}/transition-status/",
            {"target_status": "out_of_service"},
            format="json",
        )
        self.assertEqual(changed.status_code, 200)
        blocked = self.client.post(
            f"/api/v1/assets/{self.asset.pk}/transition-status/",
            {"target_status": "operational"},
            format="json",
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertTrue(
            AuditLog.objects.filter(
                entity_id=str(self.asset.pk), action="asset.status_transitioned"
            ).exists()
        )

    def test_role_boundary_and_super_admin_break_glass(self):
        for user in (self.construction, self.security):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/v1/assets/").status_code, 403)
            self.assertEqual(
                self.client.get(f"/api/v1/assets/{self.asset.pk}/").status_code,
                403,
            )
            self.assertEqual(
                self.client.post("/api/v1/assets/", self.payload(), format="json").status_code,
                403,
            )
            self.assertEqual(
                self.client.patch(
                    f"/api/v1/assets/{self.asset.pk}/",
                    {"name": "Forbidden"},
                    format="json",
                ).status_code,
                403,
            )
            self.assertEqual(
                self.client.post(
                    f"/api/v1/assets/{self.asset.pk}/transition-status/",
                    {"target_status": "under_maintenance"},
                    format="json",
                ).status_code,
                403,
            )
            self.assertEqual(
                self.client.post(
                    "/api/v1/maintenance/orders/",
                    {
                        "asset": str(self.asset.pk),
                        "asset_type": self.asset.asset_type,
                        "type": "preventive",
                        "priority": "low",
                        "description": "Forbidden maintenance request",
                        "reason": "RBAC probe",
                        "expected_execution_date": date.today().isoformat(),
                    },
                    format="json",
                ).status_code,
                403,
            )
        self.client.force_authenticate(self.super_admin)
        listed_ids = {row["id"] for row in self.client.get("/api/v1/assets/").data["results"]}
        self.assertEqual(listed_ids, {str(self.asset.pk), str(self.other_asset.pk)})
        self.assertEqual(
            self.client.get(f"/api/v1/assets/{self.other_asset.pk}/").status_code,
            200,
        )
        created = self.client.post(
            "/api/v1/assets/",
            self.payload(serial_number="ASSET-SUPER-1"),
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        asset_id = created.data["id"]
        self.assertEqual(
            self.client.patch(
                f"/api/v1/assets/{asset_id}/",
                {"model": "SUPER-EDIT"},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/assets/{asset_id}/transition-status/",
                {"target_status": "under_maintenance"},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/maintenance/orders/",
                {
                    "asset": asset_id,
                    "asset_type": "Generator",
                    "type": "preventive",
                    "priority": "low",
                    "description": "Super admin maintenance request",
                    "reason": "Scheduled check",
                    "expected_execution_date": date.today().isoformat(),
                },
                format="json",
            ).status_code,
            201,
        )

    def test_archiving_asset_with_history_is_rejected(self):
        from apps.maintenance.models import MaintenanceOrder

        MaintenanceOrder.objects.create(
            asset=self.asset,
            type=MaintenanceOrder.Type.PREVENTIVE,
            priority=MaintenanceOrder.Priority.LOW,
            description="Inspect",
            reason="Scheduled",
            expected_execution_date=date.today(),
            created_by=self.manager,
        )
        response = self.client.delete(f"/api/v1/assets/{self.asset.pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Asset.objects.filter(pk=self.asset.pk).exists())
