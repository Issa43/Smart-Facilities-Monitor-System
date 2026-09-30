from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from pypdf import PdfReader

from apps.attachments.storage import ProtectedFileSystemStorage
from apps.facilities.models import FacilityAssignment
from apps.maintenance.models import Fault
from apps.projects.management.commands.seed_demo_projects import (
    DAMASCUS_TOWER,
    HOMS,
    TARTUS,
)
from apps.projects.models import Project, ProjectAssignment, ProjectDocument
from apps.projects.services import calculate_project_progress
from apps.security.models import Incident
from apps.users.models import User


@pytest.fixture(autouse=True)
def temporary_protected_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(
        ProjectDocument._meta.get_field("file"),
        "storage",
        ProtectedFileSystemStorage(location=str(tmp_path)),
    )


@pytest.fixture
def demo_accounts(role_super_admin, role_construction_manager, role_operations_manager, role_security_officer):
    accounts = {}
    for name, role in (
        ("admin", role_super_admin),
        ("construction", role_construction_manager),
        ("operations", role_operations_manager),
        ("officer", role_security_officer),
    ):
        accounts[name] = User.objects.create_user(
            email=f"{name}@sflms.local",
            username=name,
            full_name=name,
            password="StrongPass123!",
            role=role,
        )
    return accounts


def run():
    out = StringIO()
    call_command("seed_demo_projects", stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_adds_the_three_life_cycle_projects(demo_accounts):
    run()

    tartus = Project.objects.get(name=TARTUS)
    homs = Project.objects.get(name=HOMS)
    tower = Project.objects.get(name=DAMASCUS_TOWER)

    # Progress is the plain average of the phases, as the dashboard shows it.
    assert calculate_project_progress(tartus) == Decimal("51.89")
    assert calculate_project_progress(homs) == Decimal("51.67")
    assert calculate_project_progress(tower) == Decimal("100.00")

    assert tartus.status == "in_progress" and tartus.facility is None
    assert homs.facility.name == "مجمع النور الصحي" and homs.facility.status == "under_maintenance"
    assert tower.status == "operational" and tower.facility.created_from_project == tower

    # The demo logins see every project and both facilities.
    construction = demo_accounts["construction"]
    for project in (tartus, homs, tower):
        assert ProjectAssignment.objects.filter(project=project, user=construction).exists()
    assert tartus.assignments.count() == 6
    team = User.objects.filter(project_assignments__project=tartus).exclude(pk=construction.pk)
    assert all(not member.has_usable_password() for member in team)
    assert FacilityAssignment.objects.filter(
        facility=tower.facility, user=demo_accounts["officer"], role_type="security_officer"
    ).exists()

    assert tower.facility.assets.count() == 10
    assert homs.facility.assets.count() == 6
    elevator = Fault.objects.get(asset__serial_number="JSM-ELEV-02")
    assert elevator.status == "investigating"  # left open, to resolve during the demo
    assert Fault.objects.get(asset__serial_number="NOOR-MDB-01").status == "resolved"
    smoke = Incident.objects.get(facility=tower.facility)
    assert smoke.status == "closed" and smoke.alert.source == "manual"


@pytest.mark.django_db
def test_documents_are_real_pdfs(demo_accounts):
    run()

    documents = ProjectDocument.objects.filter(project__name__in=[TARTUS, HOMS])
    assert documents.count() == 11
    risk = documents.get(original_file_name="Site_Risk_Assessment.pdf")
    assert risk.mime_type == "application/pdf"
    with risk.file.open("rb") as handle:
        assert len(PdfReader(handle).pages) >= 1


@pytest.mark.django_db
def test_running_again_adds_nothing(demo_accounts):
    run()
    counts = (Project.objects.count(), Fault.objects.count(), ProjectDocument.objects.count())

    output = run()

    assert (Project.objects.count(), Fault.objects.count(), ProjectDocument.objects.count()) == counts
    assert output.count("skipped (already exists)") == 3
