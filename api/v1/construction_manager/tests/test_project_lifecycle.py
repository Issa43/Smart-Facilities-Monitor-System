from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.projects.models import Project, ProjectAssignment, ProjectPhase
from apps.users.models import Permission, Role, User


class ConstructionProjectLifecycleApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_role, _ = Role.objects.get_or_create(
            name=Role.SUPER_ADMIN, defaults={"description": "Admin"}
        )
        cls.manager_role, _ = Role.objects.get_or_create(
            name=Role.CONSTRUCTION_MANAGER, defaults={"description": "Manager"}
        )
        for permission_name in (
            "project.view",
            "project.edit",
            "project.close",
            "stage.create",
            "stage.edit",
            "stage.delete",
            "stage.progress",
            "stage.approve",
        ):
            Permission.objects.get_or_create(
                role=cls.manager_role, permission_name=permission_name
            )
        cls.admin = User.objects.create_user(
            email="batch5-admin@example.com",
            username="batch5-admin",
            full_name="Batch 5 Admin",
            password="StrongPass123!",
            role=cls.admin_role,
        )
        cls.manager = User.objects.create_user(
            email="batch5-manager@example.com",
            username="batch5-manager",
            full_name="Batch 5 Manager",
            password="StrongPass123!",
            role=cls.manager_role,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def make_project(
        self,
        *,
        assigned=True,
        status=Project.Status.IN_PROGRESS,
        project_start=None,
    ):
        today = project_start or date.today()
        project = Project.objects.create(
            name=f"Project {Project.objects.count() + 1}",
            facility_type=Project.FacilityType.COMMERCIAL,
            description="Original project description",
            location="Cairo",
            start_date=today,
            expected_completion_date=today + timedelta(days=30),
            status=status,
            created_by=self.admin,
        )
        if assigned:
            ProjectAssignment.objects.create(
                project=project,
                user=self.manager,
                role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
                created_by=self.admin,
            )
        return project

    def make_phase(
        self,
        project,
        *,
        status=ProjectPhase.Status.NOT_STARTED,
        progress=Decimal("0.00"),
        sequence=1,
        phase_start=None,
    ):
        today = phase_start or project.start_date
        completed = status == ProjectPhase.Status.COMPLETED
        return ProjectPhase.objects.create(
            project=project,
            name=f"Phase {sequence}",
            description="Initial phase description",
            sequence_number=sequence,
            start_date=today,
            expected_completion_date=today + timedelta(days=10),
            actual_start_date=today if progress else None,
            actual_completion_date=today if completed else None,
            current_progress=progress,
            status=status,
            approved_by=self.manager if completed else None,
            approved_at=timezone.now() if completed else None,
            created_by=self.manager,
        )

    def phase_url(self, project, phase=None, action=""):
        suffix = f"{phase.id}/" if phase else ""
        if action:
            suffix += f"{action}/"
        return f"/api/v1/projects/{project.id}/phases/{suffix}"

    def test_assigned_manager_can_edit_project_metadata_only_within_scope(self):
        assigned = self.make_project()
        outside_scope = self.make_project(assigned=False)

        response = self.client.patch(
            f"/api/v1/construction/projects/{assigned.id}/",
            {
                "name": "Updated assigned project",
                "description": "Updated by the assigned manager",
                "status": Project.Status.COMPLETED,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["primary_manager_name"], self.manager.full_name)
        assigned.refresh_from_db()
        self.assertEqual(assigned.name, "Updated assigned project")
        self.assertEqual(assigned.description, "Updated by the assigned manager")
        self.assertEqual(assigned.status, Project.Status.IN_PROGRESS)

        response = self.client.patch(
            f"/api/v1/construction/projects/{outside_scope.id}/",
            {"name": "Forbidden update"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        outside_scope.refresh_from_db()
        self.assertNotEqual(outside_scope.name, "Forbidden update")

    def test_phase_edit_and_delete_obey_lifecycle_and_assignment_scope(self):
        project = self.make_project()
        editable = self.make_phase(project)
        response = self.client.patch(
            self.phase_url(project, editable),
            {"name": "Edited phase", "priority": ProjectPhase.Priority.HIGH},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Edited phase")

        response = self.client.delete(self.phase_url(project, editable))
        self.assertEqual(response.status_code, 204)

        active = self.make_phase(
            project,
            status=ProjectPhase.Status.IN_PROGRESS,
            progress=Decimal("25.00"),
            sequence=2,
        )
        response = self.client.delete(self.phase_url(project, active))
        self.assertEqual(response.status_code, 409)

        outside_project = self.make_project(assigned=False)
        outside_phase = self.make_phase(outside_project)
        response = self.client.patch(
            self.phase_url(outside_project, outside_phase),
            {"name": "Out of scope"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_phase_start_date_respects_project_lower_boundary_without_sequencing(self):
        project_start = date(2026, 9, 5)
        project = self.make_project(project_start=project_start)

        valid_schedules = (
            (1, date(2026, 9, 5), date(2026, 9, 20)),
            (2, date(2026, 9, 6), date(2026, 9, 25)),
            (3, date(2026, 9, 10), date(2026, 9, 15)),
        )
        for sequence, start_date, end_date in valid_schedules:
            response = self.client.post(
                self.phase_url(project),
                {
                    "name": f"Overlapping phase {sequence}",
                    "description": "A valid parallel construction phase.",
                    "sequence_number": sequence,
                    "start_date": start_date.isoformat(),
                    "expected_completion_date": end_date.isoformat(),
                    "priority": ProjectPhase.Priority.MEDIUM,
                },
                format="json",
            )
            self.assertEqual(response.status_code, 201, response.data)

        invalid_response = self.client.post(
            self.phase_url(project),
            {
                "name": "Pre-project phase",
                "description": "This phase starts before its parent project.",
                "sequence_number": 4,
                "start_date": "2026-09-01",
                "expected_completion_date": "2026-09-10",
                "priority": ProjectPhase.Priority.MEDIUM,
            },
            format="json",
        )

        self.assertEqual(invalid_response.status_code, 400)
        self.assertIn("start_date", invalid_response.data["error"]["details"])
        self.assertEqual(ProjectPhase.objects.filter(project=project).count(), 3)

    def test_phase_edit_rejects_pre_project_start_and_accepts_unchanged_dates(self):
        project = self.make_project(project_start=date(2026, 9, 5))
        phase = self.make_phase(project)

        unchanged_response = self.client.patch(
            self.phase_url(project, phase),
            {"name": "Edited without changing schedule"},
            format="json",
        )
        self.assertEqual(unchanged_response.status_code, 200, unchanged_response.data)

        invalid_response = self.client.patch(
            self.phase_url(project, phase),
            {"start_date": "2026-09-01"},
            format="json",
        )
        self.assertEqual(invalid_response.status_code, 400)
        self.assertIn("start_date", invalid_response.data["error"]["details"])
        phase.refresh_from_db()
        self.assertEqual(phase.start_date, date(2026, 9, 5))

    def test_phase_actual_start_cannot_precede_project_start(self):
        project = self.make_project(project_start=date(2026, 9, 5))
        phase = self.make_phase(project)
        phase.actual_start_date = date(2026, 9, 1)

        with self.assertRaisesMessage(
            ValidationError,
            "Phase actual start date cannot precede the project start date.",
        ):
            phase.full_clean()

    def test_project_start_date_cannot_move_past_existing_phase_start(self):
        project = self.make_project(project_start=date(2026, 9, 5))
        self.make_phase(project)

        response = self.client.patch(
            f"/api/v1/construction/projects/{project.id}/",
            {"start_date": "2026-09-06"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("start_date", response.data["error"]["details"])
        project.refresh_from_db()
        self.assertEqual(project.start_date, date(2026, 9, 5))

    def test_review_return_reject_reasons_and_history_are_preserved(self):
        project = self.make_project()
        phase = self.make_phase(
            project,
            status=ProjectPhase.Status.IN_PROGRESS,
            progress=Decimal("100.00"),
        )

        response = self.client.post(
            self.phase_url(project, phase, "request-modification"),
            {"reason": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            self.phase_url(project, phase, "request-modification"),
            {"reason": "Correct the concrete test evidence."},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        phase.refresh_from_db()
        self.assertEqual(phase.status, ProjectPhase.Status.NEEDS_MODIFICATION)

        response = self.client.post(
            self.phase_url(project, phase, "reject"),
            {"reason": "Safety findings remain unresolved."},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        phase.refresh_from_db()
        self.assertEqual(phase.status, ProjectPhase.Status.REJECTED)

        response = self.client.get(self.phase_url(project, phase, "review-history"))
        self.assertEqual(response.status_code, 200)
        history = response.data.get("results", response.data)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["reason"], "Safety findings remain unresolved.")
        self.assertEqual(history[1]["reason"], "Correct the concrete test evidence.")

    def test_assigned_manager_can_complete_an_eligible_project(self):
        project = self.make_project()
        self.make_phase(
            project,
            status=ProjectPhase.Status.COMPLETED,
            progress=Decimal("100.00"),
        )

        response = self.client.post(
            f"/api/v1/construction/projects/{project.id}/complete/",
            {"actual_completion_date": date.today().isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.status, Project.Status.COMPLETED)
