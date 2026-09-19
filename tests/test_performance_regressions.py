from datetime import date, timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.construction.models import DailyReport
from apps.projects.models import Project, ProjectPhase
from apps.users.models import Role, User


class ListQueryScalingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        admin_role, _ = Role.objects.get_or_create(
            name=Role.SUPER_ADMIN, defaults={"description": "Admin"}
        )
        cls.admin = User.objects.create_user(
            email="performance-admin@example.com",
            username="performance-admin",
            full_name="Performance Admin",
            password="StrongPass123!",
            role=admin_role,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def create_project(self, suffix: str) -> Project:
        today = date.today()
        project = Project.objects.create(
            name=f"Performance Project {suffix}",
            facility_type=Project.FacilityType.COMMERCIAL,
            location="Cairo",
            start_date=today,
            expected_completion_date=today + timedelta(days=30),
            status=Project.Status.IN_PROGRESS,
            created_by=self.admin,
        )
        ProjectPhase.objects.create(
            project=project,
            name=f"Phase {suffix}",
            sequence_number=1,
            start_date=today,
            expected_completion_date=today + timedelta(days=10),
            current_progress="40.00",
            created_by=self.admin,
        )
        return project

    def query_count(self, path: str) -> tuple[int, int]:
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return len(captured), len(response.data["results"])

    def test_project_list_query_count_does_not_grow_per_project(self):
        self.create_project("one")
        one_count, one_rows = self.query_count("/api/v1/projects/")

        for suffix in ("two", "three", "four", "five"):
            self.create_project(suffix)
        many_count, many_rows = self.query_count("/api/v1/projects/")

        self.assertEqual((one_rows, many_rows), (1, 5))
        self.assertLessEqual(many_count, one_count)

    def test_daily_report_list_query_count_does_not_grow_per_report(self):
        project = self.create_project("reports")
        today = date.today()

        def create_report(offset: int):
            DailyReport.objects.create(
                project=project,
                report_date=today - timedelta(days=offset),
                title=f"Report {offset}",
                weather_condition="Clear",
                workers_count=5,
                report_content="Progress recorded.",
                created_by=self.admin,
            )

        create_report(0)
        one_count, one_rows = self.query_count(
            "/api/v1/construction/daily-reports/"
        )

        for offset in range(1, 5):
            create_report(offset)
        many_count, many_rows = self.query_count(
            "/api/v1/construction/daily-reports/"
        )

        self.assertEqual((one_rows, many_rows), (1, 5))
        self.assertLessEqual(many_count, one_count)
