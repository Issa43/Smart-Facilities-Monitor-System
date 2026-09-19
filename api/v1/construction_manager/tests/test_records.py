from datetime import date, timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from apps.projects.models import Project, ProjectAssignment, ProjectDocument, ProjectPhase
from apps.users.models import Permission, Role, User


class ConstructionRecordApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        admin_role, _ = Role.objects.get_or_create(
            name=Role.SUPER_ADMIN, defaults={"description": "Admin"}
        )
        manager_role, _ = Role.objects.get_or_create(
            name=Role.CONSTRUCTION_MANAGER, defaults={"description": "Manager"}
        )
        for permission_name in ("project.view", "project.edit", "stage.approve"):
            Permission.objects.get_or_create(
                role=manager_role, permission_name=permission_name
            )
        cls.admin = User.objects.create_user(
            email="batch7-admin@example.com",
            username="batch7-admin",
            full_name="Batch 7 Admin",
            password="StrongPass123!",
            role=admin_role,
        )
        cls.manager = User.objects.create_user(
            email="batch7-manager@example.com",
            username="batch7-manager",
            full_name="Batch 7 Manager",
            password="StrongPass123!",
            role=manager_role,
        )
        cls.outsider = User.objects.create_user(
            email="batch7-outsider@example.com",
            username="batch7-outsider",
            full_name="Batch 7 Outsider",
            password="StrongPass123!",
            role=manager_role,
        )
        today = date.today()
        cls.project = Project.objects.create(
            name="Batch 7 Project",
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
        cls.phase = ProjectPhase.objects.create(
            project=cls.project,
            name="Foundation",
            description="Foundation works",
            sequence_number=1,
            start_date=today,
            expected_completion_date=today + timedelta(days=10),
            created_by=cls.manager,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    @staticmethod
    def png_upload(name="site.png"):
        image = BytesIO()
        Image.new("RGB", (2, 2), color="white").save(image, format="PNG")
        return SimpleUploadedFile(name, image.getvalue(), content_type="image/png")

    def test_daily_report_and_quality_inspection_create_and_delete(self):
        report = self.client.post(
            "/api/v1/construction/daily-reports/",
            {
                "project": str(self.project.id),
                "phase": str(self.phase.id),
                "title": "Daily foundation report",
                "summary": "Completed the scheduled foundation works.",
                "progress_percentage": "20.00",
                "workforce_count": 12,
                "report_date": date.today().isoformat(),
            },
            format="json",
        )
        self.assertEqual(report.status_code, 201)
        self.assertEqual(report.data["weather_condition"], "Not recorded")
        self.assertEqual(report.data["author_name"], self.manager.full_name)

        inspection = self.client.post(
            "/api/v1/construction/quality-inspections/",
            {
                "project": str(self.project.id),
                "phase": str(self.phase.id),
                "title": "Concrete inspection",
                "score": "92.00",
                "result": "passed",
                "notes": "All samples passed.",
            },
            format="json",
        )
        self.assertEqual(inspection.status_code, 201)
        self.assertEqual(inspection.data["inspector_name"], self.manager.full_name)

        self.assertEqual(
            self.client.delete(
                f"/api/v1/construction/daily-reports/{report.data['id']}/"
            ).status_code,
            204,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/v1/construction/quality-inspections/{inspection.data['id']}/"
            ).status_code,
            204,
        )

    def test_document_validation_download_delete_and_authorization(self):
        document = self.client.post(
            "/api/v1/construction/documents/",
            {
                "project": str(self.project.id),
                "title": "Approved notes",
                "document_type": "report",
                "file": SimpleUploadedFile(
                    "notes.pdf",
                    b"%PDF-1.4\n%%EOF\n",
                    content_type="application/pdf",
                ),
            },
            format="multipart",
        )
        self.assertEqual(document.status_code, 201)
        self.assertEqual(document.data["uploaded_by_name"], self.manager.full_name)
        stored = ProjectDocument.objects.get(pk=document.data["id"])
        with self.assertRaises(ValueError):
            _ = stored.file.url

        url = f"/api/v1/construction/documents/{stored.id}/download/"
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.delete(
                f"/api/v1/construction/documents/{stored.id}/"
            ).status_code,
            404,
        )

        self.client.force_authenticate(self.manager)
        invalid = self.client.post(
            "/api/v1/construction/documents/",
            {
                "project": str(self.project.id),
                "title": "Forged PDF",
                "document_type": "report",
                "file": SimpleUploadedFile(
                    "forged.pdf", b"not a pdf", content_type="application/pdf"
                ),
            },
            format="multipart",
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(
            self.client.delete(
                f"/api/v1/construction/documents/{stored.id}/"
            ).status_code,
            204,
        )

    def test_cross_project_phase_links_are_rejected_without_server_errors(self):
        today = date.today()
        outside_project = Project.objects.create(
            name="Outside project",
            facility_type=Project.FacilityType.COMMERCIAL,
            location="Alexandria",
            start_date=today,
            expected_completion_date=today + timedelta(days=30),
            status=Project.Status.IN_PROGRESS,
            created_by=self.admin,
        )
        outside_phase = ProjectPhase.objects.create(
            project=outside_project,
            name="Outside phase",
            sequence_number=1,
            start_date=today,
            expected_completion_date=today + timedelta(days=10),
            created_by=self.outsider,
        )

        invalid_create = self.client.post(
            "/api/v1/construction/daily-reports/",
            {
                "project": str(self.project.id),
                "phase": str(outside_phase.id),
                "title": "Invalid cross-project report",
                "summary": "This must not be persisted.",
                "progress_percentage": "10.00",
                "workforce_count": 5,
                "report_date": today.isoformat(),
            },
            format="json",
        )
        self.assertEqual(invalid_create.status_code, 400)

        report = self.client.post(
            "/api/v1/construction/daily-reports/",
            {
                "project": str(self.project.id),
                "phase": str(self.phase.id),
                "title": "Valid scoped report",
                "summary": "Created inside the assigned project.",
                "progress_percentage": "20.00",
                "workforce_count": 8,
                "report_date": today.isoformat(),
            },
            format="json",
        )
        self.assertEqual(report.status_code, 201)
        invalid_update = self.client.patch(
            f"/api/v1/construction/daily-reports/{report.data['id']}/",
            {"phase": str(outside_phase.id)},
            format="json",
        )
        self.assertEqual(invalid_update.status_code, 400)

    def test_site_photo_is_validated_scoped_downloadable_and_deletable(self):
        photo = self.client.post(
            "/api/v1/construction/site-photos/",
            {
                "project": str(self.project.id),
                "phase": str(self.phase.id),
                "caption": "Foundation progress",
                "image": self.png_upload(),
            },
            format="multipart",
        )
        self.assertEqual(photo.status_code, 201)
        url = f"/api/v1/construction/site-photos/{photo.data['id']}/download/"
        self.assertEqual(self.client.get(url).status_code, 200)

        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.delete(
                f"/api/v1/construction/site-photos/{photo.data['id']}/"
            ).status_code,
            204,
        )
        self.assertEqual(self.client.get(url).status_code, 404)
