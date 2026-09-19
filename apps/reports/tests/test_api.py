from io import BytesIO
from datetime import date
from unittest.mock import PropertyMock, patch

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.facilities.models import Facility, FacilityAssignment
from apps.projects.models import Project, ProjectAssignment
from apps.reports.models import Report, ReportTemplate
from apps.reports.services import create_report_request, create_report_template
from apps.reports.tasks import _report_href
from apps.users.models import User


def create_user(*, role, suffix, user_status=User.STATUS_ACTIVE):
    return User.objects.create_user(
        email=f"{suffix}@sflms.test",
        username=suffix,
        full_name=suffix.replace("-", " ").title(),
        password="StrongPass123!",
        role=role,
        status=user_status,
    )


def create_template(*, actor, module=Report.Module.CONSTRUCTION):
    return create_report_template(
        name=f"{module.title()} template",
        module=module,
        report_format=Report.Format.PDF,
        configuration={"title": "Domain report"},
        actor=actor,
    )


def create_report(*, actor, module=Report.Module.CONSTRUCTION):
    return create_report_request(
        report_type="Domain summary",
        module=module,
        report_format=Report.Format.PDF,
        parameters={"date_from": "2026-01-01"},
        actor=actor,
    )


def create_project_assignment(*, actor, manager, suffix):
    project = Project.objects.create(
        name=f"Project {suffix}",
        facility_type=Project.FacilityType.COMMERCIAL,
        location="Project location",
        start_date=date(2026, 1, 1),
        expected_completion_date=date(2026, 12, 31),
        created_by=actor,
    )
    ProjectAssignment.objects.create(
        project=project,
        user=manager,
        role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
        created_by=actor,
    )
    return project


def create_facility_assignment(*, actor, user, role_type, suffix):
    facility = Facility.objects.create(
        name=f"Facility {suffix}",
        type=Facility.Type.COMMERCIAL,
        location="Facility location",
        created_by=actor,
    )
    FacilityAssignment.objects.create(
        facility=facility,
        user=user,
        role_type=role_type,
        created_by=actor,
    )
    return facility


@pytest.mark.django_db
class TestReportsAPI:
    def test_report_notifications_use_valid_role_report_centres(
        self,
        role_super_admin,
        role_construction_manager,
        role_operations_manager,
        role_security_officer,
    ):
        expectations = [
            (role_super_admin, "/admin/reports"),
            (role_construction_manager, "/construction/reports"),
            (role_operations_manager, "/operations/reports"),
            (role_security_officer, "/security/reports"),
        ]
        for index, (role, expected_href) in enumerate(expectations):
            actor = create_user(role=role, suffix=f"report-link-{index}")
            assert _report_href(create_report(actor=actor)) == expected_href

    def test_super_admin_can_manage_templates(self, api_client, super_admin_user):
        api_client.force_authenticate(user=super_admin_user)
        created = api_client.post(
            reverse("api_v1:report-template-list"),
            {
                "name": "Construction overview",
                "module": Report.Module.CONSTRUCTION,
                "format": Report.Format.PDF,
                "configuration": {"title": "Overview"},
            },
            format="json",
        )
        assert created.status_code == status.HTTP_201_CREATED

        detail_url = reverse(
            "api_v1:report-template-detail",
            kwargs={"pk": created.data["id"]},
        )
        updated = api_client.patch(
            detail_url,
            {"name": "Updated overview"},
            format="json",
        )
        assert updated.status_code == status.HTTP_200_OK
        assert updated.data["name"] == "Updated overview"
        assert api_client.get(detail_url).status_code == status.HTTP_200_OK

    def test_template_access_obeys_role_module_scope(
        self,
        api_client,
        role_construction_manager,
        role_security_officer,
        super_admin_user,
    ):
        construction = create_template(actor=super_admin_user)
        security = create_template(
            actor=super_admin_user,
            module=Report.Module.SECURITY,
        )
        manager = create_user(role=role_construction_manager, suffix="report-cm")
        officer = create_user(role=role_security_officer, suffix="report-security")

        api_client.force_authenticate(user=manager)
        visible = api_client.get(reverse("api_v1:report-template-list"))
        assert [row["id"] for row in visible.data["results"]] == [
            str(construction.pk)
        ]
        assert api_client.get(
            reverse(
                "api_v1:report-template-detail",
                kwargs={"pk": security.pk},
            )
        ).status_code == status.HTTP_404_NOT_FOUND
        assert api_client.post(
            reverse("api_v1:report-template-list"),
            {},
            format="json",
        ).status_code == status.HTTP_403_FORBIDDEN

        api_client.force_authenticate(user=officer)
        officer_visible = api_client.get(reverse("api_v1:report-template-list"))
        assert [row["id"] for row in officer_visible.data["results"]] == [
            str(security.pk)
        ]

    def test_report_request_uses_service_snapshot_and_dispatches_task(
        self,
        api_client,
        role_construction_manager,
        super_admin_user,
    ):
        manager = create_user(role=role_construction_manager, suffix="request-cm")
        project = create_project_assignment(
            actor=super_admin_user,
            manager=manager,
            suffix="snapshot",
        )
        template = create_report_template(
            name="Snapshot template",
            module=Report.Module.CONSTRUCTION,
            report_format=Report.Format.PDF,
            configuration={"default_parameters": {"project_id": str(project.pk)}},
            actor=super_admin_user,
        )
        api_client.force_authenticate(user=manager)

        with patch("api.v1.reports.views.generate_report_task.delay") as delay:
            response = api_client.post(
                reverse("api_v1:report-request-list"),
                {
                    "type": "Construction summary",
                    "module": Report.Module.CONSTRUCTION,
                    "format": Report.Format.PDF,
                    "parameters": {},
                    "template": str(template.pk),
                },
                format="json",
            )

        assert response.status_code == status.HTTP_202_ACCEPTED
        report = Report.objects.get(pk=response.data["id"])
        assert report.status == Report.Status.QUEUED
        assert report.parameters["_template_id"] == str(template.pk)
        assert "_template_configuration" in report.parameters
        assert "_template_id" not in response.data["parameters"]
        assert response.data["file_size"] is None
        delay.assert_called_once_with(str(report.pk))

    def test_completed_report_response_exposes_file_size(
        self,
        api_client,
        role_construction_manager,
    ):
        owner = create_user(role=role_construction_manager, suffix="size-cm")
        report = create_report(actor=owner)
        report.status = Report.Status.COMPLETED
        report.file_path.name = "reports/construction/sized.pdf"
        report.save(update_fields=["status", "file_path", "updated_at"])
        api_client.force_authenticate(user=owner)

        with patch.object(
            type(report.file_path),
            "size",
            new_callable=PropertyMock,
            return_value=1517,
        ):
            response = api_client.get(
                reverse("api_v1:report-request-detail", kwargs={"pk": report.pk})
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["file_size"] == 1517

    def test_invalid_parameters_and_reserved_lifecycle_fields_are_rejected(
        self,
        api_client,
        role_construction_manager,
    ):
        manager = create_user(role=role_construction_manager, suffix="invalid-cm")
        api_client.force_authenticate(user=manager)
        url = reverse("api_v1:report-request-list")
        base = {
            "type": "Construction summary",
            "module": Report.Module.CONSTRUCTION,
            "format": Report.Format.PDF,
        }

        invalid = api_client.post(url, {**base, "parameters": []}, format="json")
        assert invalid.status_code == status.HTTP_400_BAD_REQUEST
        forged = api_client.post(
            url,
            {
                **base,
                "parameters": {},
                "status": Report.Status.COMPLETED,
                "file_path": "public/report.pdf",
            },
            format="json",
        )
        assert forged.status_code == status.HTTP_400_BAD_REQUEST
        assert Report.objects.count() == 0

    def test_construction_request_validates_project_and_date_contract(
        self,
        api_client,
        role_construction_manager,
        super_admin_user,
    ):
        manager = create_user(role=role_construction_manager, suffix="contract-cm")
        project = create_project_assignment(
            actor=super_admin_user,
            manager=manager,
            suffix="contract",
        )
        api_client.force_authenticate(user=manager)
        url = reverse("api_v1:report-request-list")
        base = {
            "type": "Construction Project Report",
            "module": Report.Module.CONSTRUCTION,
            "format": Report.Format.PDF,
        }

        for parameters in (
            {},
            {"project_id": str(project.pk), "date_from": "2026-01-01"},
            {
                "project_id": str(project.pk),
                "date_from": "2026-02-01",
                "date_to": "2026-01-01",
            },
            {"project_id": str(project.pk), "status": "in_progress"},
        ):
            response = api_client.post(
                url,
                {**base, "parameters": parameters},
                format="json",
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST

        with patch("api.v1.reports.views.generate_report_task.delay") as delay:
            accepted = api_client.post(
                url,
                {
                    **base,
                    "parameters": {
                        "project_id": str(project.pk),
                        "date_from": "2026-01-01",
                        "date_to": "2026-01-31",
                        "period_label": "January 2026",
                    },
                },
                format="json",
            )
        assert accepted.status_code == status.HTTP_202_ACCEPTED
        delay.assert_called_once()

    def test_report_requests_are_immutable_and_owner_scoped(
        self,
        api_client,
        role_construction_manager,
        super_admin_user,
    ):
        owner = create_user(role=role_construction_manager, suffix="owner-cm")
        other = create_user(role=role_construction_manager, suffix="other-cm")
        report = create_report(actor=owner)
        detail_url = reverse(
            "api_v1:report-request-detail",
            kwargs={"pk": report.pk},
        )

        api_client.force_authenticate(user=owner)
        assert api_client.patch(
            detail_url,
            {"status": Report.Status.COMPLETED},
            format="json",
        ).status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        api_client.force_authenticate(user=other)
        assert api_client.get(detail_url).status_code == status.HTTP_404_NOT_FOUND
        api_client.force_authenticate(user=super_admin_user)
        assert api_client.get(detail_url).status_code == status.HTTP_200_OK

    def test_role_module_generation_matrix_and_inactive_denial(
        self,
        api_client,
        role_construction_manager,
        role_operations_manager,
        role_security_officer,
        super_admin_user,
    ):
        url = reverse("api_v1:report-request-list")
        manager = create_user(role=role_construction_manager, suffix="matrix-0")
        project = create_project_assignment(
            actor=super_admin_user,
            manager=manager,
            suffix="matrix",
        )
        operations = create_user(role=role_operations_manager, suffix="matrix-1")
        operations_facility = create_facility_assignment(
            actor=super_admin_user,
            user=operations,
            role_type=FacilityAssignment.RoleType.OPERATIONS_MANAGER,
            suffix="operations",
        )
        officer = create_user(role=role_security_officer, suffix="matrix-2")
        security_facility = create_facility_assignment(
            actor=super_admin_user,
            user=officer,
            role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
            suffix="security",
        )
        cases = [
            (
                manager,
                Report.Module.CONSTRUCTION,
                {"project_id": str(project.pk)},
                Report.Module.SECURITY,
            ),
            (
                operations,
                Report.Module.ASSETS,
                {"facility_id": str(operations_facility.pk)},
                Report.Module.CONSTRUCTION,
            ),
            (
                officer,
                Report.Module.SECURITY,
                {"facility_id": str(security_facility.pk)},
                Report.Module.ASSETS,
            ),
        ]
        for user, allowed, parameters, denied in cases:
            api_client.force_authenticate(user=user)
            with patch("api.v1.reports.views.generate_report_task.delay"):
                accepted = api_client.post(
                    url,
                    {
                        "type": "Allowed",
                        "module": allowed,
                        "format": Report.Format.PDF,
                        "parameters": parameters,
                    },
                    format="json",
                )
            assert accepted.status_code == status.HTTP_202_ACCEPTED
            rejected = api_client.post(
                url,
                {
                    "type": "Denied",
                    "module": denied,
                    "format": Report.Format.PDF,
                    "parameters": {},
                },
                format="json",
            )
            assert rejected.status_code == status.HTTP_403_FORBIDDEN

        inactive = create_user(
            role=role_security_officer,
            suffix="inactive-reports",
            user_status=User.STATUS_SUSPENDED,
        )
        api_client.force_authenticate(user=inactive)
        assert api_client.get(url).status_code == status.HTTP_403_FORBIDDEN

    @override_settings(CORS_ALLOWED_ORIGINS=["http://127.0.0.1:4173"])
    def test_completed_report_download_is_protected(
        self,
        api_client,
        role_construction_manager,
    ):
        owner = create_user(role=role_construction_manager, suffix="download-cm")
        report = create_report(actor=owner)
        report.status = Report.Status.COMPLETED
        report.file_path.name = "reports/construction/protected.pdf"
        report.save(update_fields=["status", "file_path", "updated_at"])
        api_client.force_authenticate(user=owner)
        stream = BytesIO(b"%PDF-1.4 protected")
        stream.name = report.file_path.name

        with patch(
            "api.v1.reports.views.open_authorized_protected_file",
            return_value=stream,
        ) as protected_open:
            response = api_client.get(
                reverse("api_v1:report-request-download", kwargs={"pk": report.pk}),
                HTTP_ORIGIN="http://127.0.0.1:4173",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Length"] == str(len(b"%PDF-1.4 protected"))
        assert "attachment" in response["Content-Disposition"]
        exposed_headers = {
            header.strip().lower()
            for header in response["Access-Control-Expose-Headers"].split(",")
        }
        assert {"content-disposition", "content-length"} <= exposed_headers
        assert "file_path" not in api_client.get(
            reverse("api_v1:report-request-detail", kwargs={"pk": report.pk})
        ).data
        protected_open.assert_called_once_with(owner, report, "file_path")

    def test_completed_excel_download_uses_xlsx_content_type(
        self,
        api_client,
        role_construction_manager,
    ):
        owner = create_user(role=role_construction_manager, suffix="xlsx-download-cm")
        report = create_report(actor=owner)
        report.format = Report.Format.EXCEL
        report.status = Report.Status.COMPLETED
        report.file_path.name = "reports/construction/protected.xlsx"
        report.save(update_fields=["format", "status", "file_path", "updated_at"])
        api_client.force_authenticate(user=owner)
        stream = BytesIO(b"PK\x03\x04 protected")
        stream.name = report.file_path.name

        with patch(
            "api.v1.reports.views.open_authorized_protected_file",
            return_value=stream,
        ):
            response = api_client.get(
                reverse("api_v1:report-request-download", kwargs={"pk": report.pk})
            )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert response["Content-Length"] == str(len(b"PK\x03\x04 protected"))
        assert response["Content-Disposition"].endswith('.xlsx"')

    def test_incomplete_report_download_is_blocked(
        self,
        api_client,
        role_construction_manager,
    ):
        owner = create_user(role=role_construction_manager, suffix="pending-cm")
        report = create_report(actor=owner)
        api_client.force_authenticate(user=owner)

        response = api_client.get(
            reverse("api_v1:report-request-download", kwargs={"pk": report.pk})
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["error"]["code"] == status.HTTP_409_CONFLICT

    def test_failed_report_retry_is_owner_scoped_and_requeues(
        self,
        api_client,
        role_construction_manager,
    ):
        owner = create_user(role=role_construction_manager, suffix="retry-owner")
        other = create_user(role=role_construction_manager, suffix="retry-other")
        report = create_report(actor=owner)
        report.status = Report.Status.FAILED
        report.parameters = {**report.parameters, "_generation_error": "Temporary failure"}
        report.save(update_fields=["status", "parameters", "updated_at"])
        retry_url = reverse("api_v1:report-request-retry", kwargs={"pk": report.pk})

        api_client.force_authenticate(user=other)
        assert api_client.post(retry_url).status_code == status.HTTP_404_NOT_FOUND
        api_client.force_authenticate(user=owner)
        with patch("api.v1.reports.views.generate_report_task.delay") as delay:
            retried = api_client.post(retry_url)

        assert retried.status_code == status.HTTP_202_ACCEPTED
        assert retried.data["status"] == Report.Status.QUEUED
        assert retried.data["failure_details"] is None
        delay.assert_called_once_with(str(report.pk))
