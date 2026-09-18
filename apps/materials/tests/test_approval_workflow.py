from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.materials.models import Material, MaterialRequest
from apps.projects.models import Project, ProjectAssignment
from apps.users.models import Permission, Role, User


class MaterialRequestApprovalWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.roles = {
            name: Role.objects.get_or_create(name=name, defaults={"description": name})[0]
            for name in (
                Role.SUPER_ADMIN,
                Role.CONSTRUCTION_MANAGER,
                Role.OPERATIONS_MANAGER,
                Role.SECURITY_OFFICER,
            )
        }
        Permission.objects.get_or_create(
            role=cls.roles[Role.CONSTRUCTION_MANAGER],
            permission_name="material.request",
        )
        cls.admin = cls.create_user("admin", Role.SUPER_ADMIN)
        cls.manager = cls.create_user("manager", Role.CONSTRUCTION_MANAGER)
        cls.other_manager = cls.create_user("other-manager", Role.CONSTRUCTION_MANAGER)
        cls.operations = cls.create_user("operations", Role.OPERATIONS_MANAGER)
        cls.security = cls.create_user("security", Role.SECURITY_OFFICER)

        today = date.today()
        cls.project = Project.objects.create(
            name="Approval project",
            facility_type=Project.FacilityType.COMMERCIAL,
            location="Cairo",
            start_date=today,
            expected_completion_date=today + timedelta(days=90),
            status=Project.Status.IN_PROGRESS,
            created_by=cls.admin,
        )
        cls.other_project = Project.objects.create(
            name="Isolated project",
            facility_type=Project.FacilityType.COMMERCIAL,
            location="Giza",
            start_date=today,
            expected_completion_date=today + timedelta(days=90),
            status=Project.Status.IN_PROGRESS,
            created_by=cls.admin,
        )
        for user in (cls.manager, cls.other_manager):
            ProjectAssignment.objects.create(
                project=cls.project,
                user=user,
                role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
                created_by=cls.admin,
            )
        cls.material = Material.objects.create(
            project=cls.project,
            name="Cement",
            unit=Material.Unit.BAG,
            quantity_required=Decimal("100.000"),
            quantity_used=Decimal("0.000"),
            quantity_remaining=Decimal("100.000"),
            min_stock_threshold=Decimal("10.000"),
            created_by=cls.manager,
        )
        cls.other_material = Material.objects.create(
            project=cls.other_project,
            name="Steel",
            unit=Material.Unit.TONNE,
            quantity_required=Decimal("20.000"),
            quantity_used=Decimal("0.000"),
            quantity_remaining=Decimal("20.000"),
            min_stock_threshold=Decimal("2.000"),
            created_by=cls.admin,
        )

    @classmethod
    def create_user(cls, prefix, role_name):
        return User.objects.create_user(
            email=f"{prefix}@example.test",
            username=prefix,
            full_name=prefix.replace("-", " ").title(),
            password="StrongPass123!",
            role=cls.roles[role_name],
        )

    def setUp(self):
        self.client = APIClient()

    def authenticate(self, user):
        self.client.force_authenticate(user)

    def create_request(self, *, creator=None, project=None, material=None):
        return MaterialRequest.objects.create(
            project=project or self.project,
            material=material or self.material,
            quantity_requested=Decimal("12.000"),
            reason="Required for the current construction phase.",
            priority=MaterialRequest.Priority.HIGH,
            created_by=creator or self.manager,
        )

    def action(self, request_obj, action):
        return self.client.post(
            f"/api/v1/construction/material-requests/{request_obj.id}/{action}/"
        )

    def test_construction_manager_can_create_and_delete_but_cannot_decide(self):
        self.authenticate(self.manager)
        response = self.client.post(
            "/api/v1/construction/material-requests/",
            {
                "project": str(self.project.id),
                "material": str(self.material.id),
                "quantity_requested": "5.000",
                "reason": "Needed on site.",
                "priority": MaterialRequest.Priority.MEDIUM,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], MaterialRequest.Status.SUBMITTED)
        self.assertEqual(response.data["project_name"], self.project.name)
        self.assertEqual(response.data["requested_by_name"], self.manager.full_name)

        own_request = MaterialRequest.objects.get(pk=response.data["id"])
        self.assertEqual(self.action(own_request, "approve").status_code, 403)
        self.assertEqual(self.action(own_request, "reject").status_code, 403)

        another_request = self.create_request(creator=self.other_manager)
        self.assertEqual(self.action(another_request, "approve").status_code, 403)
        self.assertEqual(self.action(another_request, "review").status_code, 403)
        own_request.refresh_from_db()
        another_request.refresh_from_db()
        self.assertEqual(own_request.status, MaterialRequest.Status.SUBMITTED)
        self.assertEqual(another_request.status, MaterialRequest.Status.SUBMITTED)

        self.assertEqual(
            self.client.delete(
                f"/api/v1/construction/material-requests/{own_request.id}/"
            ).status_code,
            204,
        )

    def test_operations_and_security_cannot_approve_or_reject(self):
        for user in (self.operations, self.security):
            request_obj = self.create_request()
            self.authenticate(user)
            self.assertEqual(self.action(request_obj, "approve").status_code, 403)
            self.assertEqual(self.action(request_obj, "reject").status_code, 403)
            request_obj.refresh_from_db()
            self.assertEqual(request_obj.status, MaterialRequest.Status.SUBMITTED)

    def test_super_admin_has_global_list_retrieve_review_and_approval(self):
        scoped = self.create_request()
        isolated = self.create_request(
            creator=self.admin,
            project=self.other_project,
            material=self.other_material,
        )
        self.authenticate(self.admin)

        listing = self.client.get("/api/v1/construction/material-requests/")
        self.assertEqual(listing.status_code, 200)
        ids = {str(item["id"]) for item in listing.data["results"]}
        self.assertTrue({str(scoped.id), str(isolated.id)}.issubset(ids))
        detail = self.client.get(
            f"/api/v1/construction/material-requests/{scoped.id}/"
        )
        self.assertEqual(detail.status_code, 200)

        review = self.action(scoped, "review")
        self.assertEqual(review.status_code, 200)
        self.assertEqual(review.data["status"], MaterialRequest.Status.REVIEWED)
        approve = self.action(scoped, "approve")
        self.assertEqual(approve.status_code, 200)
        self.assertEqual(approve.data["status"], MaterialRequest.Status.APPROVED)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                entity_id=str(scoped.id),
                action="material_request.reviewed",
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                entity_id=str(scoped.id),
                action="material_request.approved",
            ).exists()
        )

    def test_super_admin_can_atomically_approve_submitted_or_reject_reviewable(self):
        submitted = self.create_request()
        reviewable = self.create_request()
        self.authenticate(self.admin)

        approve = self.action(submitted, "approve")
        self.assertEqual(approve.status_code, 200)
        submitted.refresh_from_db()
        self.assertEqual(submitted.status, MaterialRequest.Status.APPROVED)

        self.assertEqual(self.action(reviewable, "review").status_code, 200)
        reject = self.action(reviewable, "reject")
        self.assertEqual(reject.status_code, 200)
        reviewable.refresh_from_db()
        self.assertEqual(reviewable.status, MaterialRequest.Status.REJECTED)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                entity_id=str(reviewable.id),
                action="material_request.rejected",
            ).exists()
        )

        invalid = self.action(reviewable, "approve")
        self.assertEqual(invalid.status_code, 409)
        reviewable.refresh_from_db()
        self.assertEqual(reviewable.status, MaterialRequest.Status.REJECTED)

    def test_creator_self_approval_guard_remains_enforced(self):
        request_obj = self.create_request(creator=self.admin)
        self.authenticate(self.admin)

        response = self.action(request_obj, "approve")

        self.assertEqual(response.status_code, 409)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, MaterialRequest.Status.SUBMITTED)

    def test_construction_manager_visibility_remains_project_scoped(self):
        visible = self.create_request()
        hidden = self.create_request(
            creator=self.admin,
            project=self.other_project,
            material=self.other_material,
        )
        self.authenticate(self.manager)

        listing = self.client.get("/api/v1/construction/material-requests/")
        self.assertEqual(listing.status_code, 200)
        ids = {str(item["id"]) for item in listing.data["results"]}
        self.assertIn(str(visible.id), ids)
        self.assertNotIn(str(hidden.id), ids)
        self.assertEqual(
            self.client.get(
                f"/api/v1/construction/material-requests/{hidden.id}/"
            ).status_code,
            404,
        )
