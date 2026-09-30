"""Security reports: real data in, Security-styled PDF/XLSX out."""

import io
import re
import zipfile
from datetime import datetime, timezone
from xml.etree import ElementTree

import pytest
from django.core.exceptions import ValidationError
from pypdf import PdfReader
from rest_framework import status

from apps.attachments.storage import ProtectedFileSystemStorage
from apps.facilities.models import Facility, FacilityAssignment
from apps.reports.models import Report
from apps.reports.services import (
    OPERATIONS_EMPTY_MESSAGE,
    REPORT_ACCENT,
    REPORT_ACCENT_DARK,
    SECURITY_REPORT_PALETTE,
    SECURITY_REPORT_TITLES,
    _argb,
    create_report_request,
    generate_report,
)
from apps.security.models import Incident, IncidentAction, SecurityAlert
from apps.users.models import User

NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@pytest.fixture(autouse=True)
def temporary_protected_storage(monkeypatch, tmp_path):
    # The FileField resolves its storage at import time, so point that
    # instance at a temporary directory instead of the real protected media.
    monkeypatch.setattr(
        Report._meta.get_field("file_path"),
        "storage",
        ProtectedFileSystemStorage(location=str(tmp_path)),
    )


@pytest.fixture
def security_world(role_security_officer):
    officer = User.objects.create_user(
        email="report-officer@sflms.test",
        username="report-officer",
        full_name="Report Officer",
        password="StrongPass123!",
        role=role_security_officer,
    )
    site = Facility.objects.create(name="Harbour Gate", type="industrial", location="Aqaba", created_by=officer)
    other = Facility.objects.create(name="Inland Depot", type="industrial", location="Zarqa", created_by=officer)
    FacilityAssignment.objects.create(
        facility=site, user=officer, role_type=FacilityAssignment.RoleType.SECURITY_OFFICER, created_by=officer
    )

    def incident(facility, number, severity, state, created):
        record = Incident.objects.create(
            incident_number=number,
            facility=facility,
            incident_type="Intrusion",
            description=f"{number} description",
            location="Gate 2",
            severity_level=severity,
            status=state,
            created_by=officer,
        )
        Incident.objects.filter(pk=record.pk).update(created_at=created)
        return record

    first = incident(site, "INC-SITE-JAN-000001", "high", "open", datetime(2026, 1, 5, tzinfo=timezone.utc))
    incident(site, "INC-SITE-FEB-000002", "critical", "investigation", datetime(2026, 2, 5, tzinfo=timezone.utc))
    incident(other, "INC-OTHER-JAN-00003", "low", "open", datetime(2026, 1, 6, tzinfo=timezone.utc))
    IncidentAction.objects.create(
        incident=first, action_taken="Sealed the north gate", notes="Guard 7", taken_by=officer, created_by=officer
    )
    for alert_type, severity in (("fire", "critical"), ("intrusion", "high"), ("intrusion", "high")):
        SecurityAlert.objects.create(
            facility=site, alert_type=alert_type, location="Yard", severity_level=severity,
            source="ai_detection", created_by=officer,
        )
    SecurityAlert.objects.create(
        facility=other, alert_type="smoke", location="Store", severity_level="critical",
        source="ai_detection", created_by=officer,
    )
    return officer, site, other


def _generate(officer, module, report_format, parameters, report_type="incidents"):
    report = create_report_request(
        report_type=report_type, module=module, report_format=report_format,
        parameters=parameters, actor=officer,
    )
    return generate_report(report_id=report.pk)


def _pdf_text(report):
    with report.file_path.open("rb") as handle:
        reader = PdfReader(io.BytesIO(handle.read()))
    return reader, "\n".join(page.extract_text() or "" for page in reader.pages)


def _xlsx(report):
    with report.file_path.open("rb") as handle, zipfile.ZipFile(io.BytesIO(handle.read())) as workbook:
        styles = workbook.read("xl/styles.xml").decode()
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in sheet.find("x:sheetData", NS):
        values = []
        for cell in row:
            inline = cell.find("x:is/x:t", NS)
            value = cell.find("x:v", NS)
            values.append((inline.text if inline is not None else value.text if value is not None else "") or "")
        rows.append(values)
    return styles, sheet, rows


@pytest.mark.django_db
def test_incident_pdf_is_security_branded_and_matches_the_database(security_world):
    officer, site, _ = security_world
    report = _generate(officer, Report.Module.SECURITY, Report.Format.PDF, {"facility_id": str(site.pk)})
    reader, text = _pdf_text(report)
    expected = list(Incident.objects.filter(facility=site).values_list("incident_number", flat=True))

    assert report.status == Report.Status.COMPLETED
    assert SECURITY_REPORT_TITLES[Report.Module.SECURITY] in text
    assert "SFLMS Security Report" in text
    assert "Operations Report" not in text
    assert all("SFLMS | Security Report" in (page.extract_text() or "") for page in reader.pages)
    assert "Harbour Gate" in text  # scoped facility named, as Construction names its project
    assert int(re.search(r"Records\s+(\d+)", text).group(1)) == len(expected) == 2
    for number in expected:  # identifiers stay on one line
        assert number in text
    assert "INC-OTHER-JAN-00003" not in text
    assert "Incident Number" in text and "Incident Incident Number" not in text


@pytest.mark.django_db
def test_incident_xlsx_uses_the_red_palette_and_database_rows(security_world):
    officer, site, _ = security_world
    report = _generate(officer, Report.Module.SECURITY, Report.Format.EXCEL, {"facility_id": str(site.pk)})
    styles, sheet, rows = _xlsx(report)
    header = rows.index(next(r for r in rows if r and r[0] == "Incident Number"))
    data = rows[header + 1:]

    assert _argb(SECURITY_REPORT_PALETTE["accent"]) in styles
    assert _argb(SECURITY_REPORT_PALETTE["accent_dark"]) in styles
    assert _argb(REPORT_ACCENT) not in styles and _argb(REPORT_ACCENT_DARK) not in styles
    assert rows[0][0] == f"SFLMS - {SECURITY_REPORT_TITLES[Report.Module.SECURITY]}"
    assert sorted(r[0] for r in data) == ["INC-SITE-FEB-000002", "INC-SITE-JAN-000001"]
    assert sorted((r[5], r[6]) for r in data) == [("critical", "investigation"), ("high", "open")]
    assert sheet.find("x:sheetViews/x:sheetView/x:pane", NS).get("state") == "frozen"
    assert sheet.find("x:autoFilter", NS) is not None


@pytest.mark.django_db
def test_alert_counts_match_the_database_per_type(security_world):
    officer, site, _ = security_world
    report = _generate(officer, Report.Module.ALERTS, Report.Format.EXCEL, {"facility_id": str(site.pk)}, "alerts")
    _, _, rows = _xlsx(report)
    header = rows.index(next(r for r in rows if r and r[0] == "Facility ID"))
    data = rows[header + 1:]
    counted = {}
    for row in data:
        counted[(row[1], row[3])] = counted.get((row[1], row[3]), 0) + 1
    expected = {}
    for alert_type, severity in SecurityAlert.objects.filter(facility=site).values_list("alert_type", "severity_level"):
        expected[(alert_type, severity)] = expected.get((alert_type, severity), 0) + 1

    assert counted == expected == {("fire", "critical"): 1, ("intrusion", "high"): 2}
    assert "False Positive" in rows[header]
    assert rows[0][0] == f"SFLMS - {SECURITY_REPORT_TITLES[Report.Module.ALERTS]}"


@pytest.mark.django_db
def test_response_report_labels_and_rows(security_world):
    officer, site, _ = security_world
    report = _generate(officer, Report.Module.RESPONSE, Report.Format.PDF, {"facility_id": str(site.pk)}, "response")
    _, text = _pdf_text(report)

    assert SECURITY_REPORT_TITLES[Report.Module.RESPONSE] in text
    assert "Sealed the north gate" in text and "Guard 7" in text
    assert "INC-SITE-JAN-000001" in text
    assert "Taken By (User ID)" in text and "Taken By Id" not in text


@pytest.mark.django_db
def test_date_and_status_filters_come_from_the_query(security_world):
    officer, site, _ = security_world
    january = _generate(officer, Report.Module.SECURITY, Report.Format.PDF, {
        "facility_id": str(site.pk), "date_from": "2026-01-01", "date_to": "2026-01-31",
    })
    investigating = _generate(officer, Report.Module.SECURITY, Report.Format.PDF, {
        "facility_id": str(site.pk), "status": "investigation",
    })
    _, january_text = _pdf_text(january)
    _, status_text = _pdf_text(investigating)

    assert "INC-SITE-JAN-000001" in january_text and "INC-SITE-FEB-000002" not in january_text
    assert "2026-01-01 to 2026-01-31" in january_text
    assert "INC-SITE-FEB-000002" in status_text and "INC-SITE-JAN-000001" not in status_text


@pytest.mark.django_db
def test_empty_period_renders_the_empty_state_not_placeholder_rows(security_world):
    officer, site, _ = security_world
    pdf = _generate(officer, Report.Module.SECURITY, Report.Format.PDF, {
        "facility_id": str(site.pk), "date_from": "2030-01-01", "date_to": "2030-01-31",
    })
    xlsx = _generate(officer, Report.Module.SECURITY, Report.Format.EXCEL, {
        "facility_id": str(site.pk), "date_from": "2030-01-01", "date_to": "2030-01-31",
    })
    _, text = _pdf_text(pdf)
    _, _, rows = _xlsx(xlsx)

    assert OPERATIONS_EMPTY_MESSAGE in text
    assert int(re.search(r"Records\s+(\d+)", text).group(1)) == 0
    assert any(OPERATIONS_EMPTY_MESSAGE in cell for row in rows for cell in row)
    assert not any("INC-" in cell for row in rows for cell in row)


@pytest.mark.django_db
def test_template_title_still_overrides_the_security_default(security_world):
    officer, site, _ = security_world
    report = create_report_request(
        report_type="incidents", module=Report.Module.SECURITY, report_format=Report.Format.PDF,
        parameters={"facility_id": str(site.pk), "_template_configuration": {"title": "Night Shift Incidents"}},
        actor=officer,
    )
    _, text = _pdf_text(generate_report(report_id=report.pk))
    assert "Night Shift Incidents" in text


@pytest.mark.django_db
def test_unsupported_filter_fails_the_report(security_world):
    officer, site, _ = security_world
    report = create_report_request(
        report_type="incidents", module=Report.Module.SECURITY, report_format=Report.Format.PDF,
        parameters={"facility_id": str(site.pk), "severity": "high"}, actor=officer,
    )
    with pytest.raises(ValidationError):
        generate_report(report_id=report.pk)
    report.refresh_from_db()
    assert report.status == Report.Status.FAILED


@pytest.mark.django_db
def test_officer_scope_is_enforced_by_the_api(security_world, api_client):
    officer, site, other = security_world
    api_client.force_authenticate(officer)

    def request(module, parameters):
        return api_client.post(
            "/api/v1/reports/requests/",
            {"type": "incidents", "module": module, "format": "pdf", "parameters": parameters},
            format="json",
        )

    assert request("security", {}).status_code == status.HTTP_403_FORBIDDEN
    assert request("security", {"facility_id": str(other.pk)}).status_code == status.HTTP_403_FORBIDDEN
    assert request("assets", {"facility_id": str(site.pk)}).status_code == status.HTTP_403_FORBIDDEN
    assert request("security", {"facility_id": str(site.pk)}).status_code == status.HTTP_202_ACCEPTED
    api_client.force_authenticate(None)
    assert request("security", {"facility_id": str(site.pk)}).status_code == status.HTTP_401_UNAUTHORIZED
