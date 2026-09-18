import os
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.facilities.models import Facility, FacilityAssignment
from apps.projects.models import Project, ProjectAssignment, ProjectPhase
from apps.users.models import Role, User


class Command(BaseCommand):
    help = "Create deterministic users and scoped records in the disposable E2E database."

    @transaction.atomic
    def handle(self, *args, **options):
        database_name = str(connection.settings_dict.get("NAME", ""))
        if "e2e" not in database_name.lower():
            raise CommandError("Refusing to seed a database whose name does not contain 'e2e'.")

        password = os.environ.get("E2E_TEST_PASSWORD")
        if not password:
            raise CommandError("E2E_TEST_PASSWORD is required.")

        users = {}
        for role_name in (
            Role.SUPER_ADMIN,
            Role.CONSTRUCTION_MANAGER,
            Role.OPERATIONS_MANAGER,
            Role.SECURITY_OFFICER,
        ):
            role = Role.objects.get(name=role_name)
            username = f"e2e_{role_name}"
            user, _ = User.objects.update_or_create(
                username=username,
                defaults={
                    "email": f"{username}@example.test",
                    "full_name": f"E2E {role.get_name_display()}",
                    "role": role,
                    "status": User.STATUS_ACTIVE,
                },
            )
            user.set_password(password)
            user.save(update_fields=["password", "updated_at"])
            users[role_name] = user

        inactive, _ = User.objects.update_or_create(
            username="e2e_inactive",
            defaults={
                "email": "e2e_inactive@example.test",
                "full_name": "E2E Inactive User",
                "role": Role.objects.get(name=Role.OPERATIONS_MANAGER),
                "status": User.STATUS_INACTIVE,
            },
        )
        inactive.set_password(password)
        inactive.save(update_fields=["password", "updated_at"])

        admin = users[Role.SUPER_ADMIN]
        today = date.today()
        project, _ = Project.objects.update_or_create(
            name="E2E Assigned Project",
            defaults={
                "facility_type": Project.FacilityType.COMMERCIAL,
                "location": "E2E Cairo",
                "start_date": today,
                "expected_completion_date": today + timedelta(days=90),
                "status": Project.Status.IN_PROGRESS,
                "created_by": admin,
            },
        )
        Project.objects.update_or_create(
            name="E2E Foreign Project",
            defaults={
                "facility_type": Project.FacilityType.INDUSTRIAL,
                "location": "E2E Alexandria",
                "start_date": today,
                "expected_completion_date": today + timedelta(days=120),
                "status": Project.Status.IN_PROGRESS,
                "created_by": admin,
            },
        )
        ProjectAssignment.objects.get_or_create(
            project=project,
            user=users[Role.CONSTRUCTION_MANAGER],
            role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
            defaults={"created_by": admin},
        )
        ProjectPhase.objects.update_or_create(
            project=project,
            sequence_number=1,
            defaults={
                "name": "E2E Self Approval Phase",
                "description": "Created by the assigned manager.",
                "start_date": today,
                "expected_completion_date": today + timedelta(days=30),
                "created_by": users[Role.CONSTRUCTION_MANAGER],
            },
        )

        facility, _ = Facility.objects.update_or_create(
            name="E2E Assigned Facility",
            defaults={
                "type": Facility.Type.COMMERCIAL,
                "location": "E2E Cairo",
                "operation_start_date": today,
                "status": Facility.Status.OPERATIONAL,
                "created_by": admin,
            },
        )
        Facility.objects.update_or_create(
            name="E2E Foreign Facility",
            defaults={
                "type": Facility.Type.INDUSTRIAL,
                "location": "E2E Alexandria",
                "operation_start_date": today,
                "status": Facility.Status.OPERATIONAL,
                "created_by": admin,
            },
        )
        for role_name, assignment_type in (
            (Role.OPERATIONS_MANAGER, FacilityAssignment.RoleType.OPERATIONS_MANAGER),
            (Role.SECURITY_OFFICER, FacilityAssignment.RoleType.SECURITY_OFFICER),
        ):
            FacilityAssignment.objects.get_or_create(
                facility=facility,
                user=users[role_name],
                role_type=assignment_type,
                defaults={"created_by": admin},
            )

        self.stdout.write(self.style.SUCCESS("Disposable E2E fixtures are ready."))
