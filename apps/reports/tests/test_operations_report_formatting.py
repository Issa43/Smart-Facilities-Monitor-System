import io
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
from pypdf import PdfReader

from apps.assets.models import Asset
from apps.facilities.models import Facility
from apps.maintenance.models import Fault
from apps.reports.models import Report
from apps.reports.services import (
    OPERATIONS_EMPTY_MESSAGE,
    REPORT_ACCENT,
    REPORT_ACCENT_DARK,
    REPORT_ACCENT_LIGHT,
    _argb,
    _operations_column_label,
    _render_operations_pdf,
    _render_operations_xlsx,
    build_domain_report_rows,
    create_report_request,
    generate_report,
)
from apps.users.models import User


OPERATIONS_CASES = (
    (
        Report.Module.MAINTENANCE,
        "Maintenance Report",
        ("asset_id", "description", "expected_execution_date", "status"),
        {
            "asset_id": "asset-101",
            "description": "Preventive maintenance inspection",
            "expected_execution_date": date(2026, 9, 20),
            "status": "open",
        },
    ),
    (
        Report.Module.ASSETS,
        "Assets Report",
        ("facility_id", "name", "asset_type", "health_score"),
        {
            "facility_id": "facility-101",
            "name": "Primary Chiller",
            "asset_type": "Chiller",
            "health_score": Decimal("81.00"),
        },
    ),
    (
        Report.Module.FAULTS,
        "Faults Report",
        ("asset_id", "fault_type", "description", "discovery_time"),
        {
            "asset_id": "asset-101",
            "fault_type": "Pressure drop",
            "description": "Pressure fell below the operating threshold",
            "discovery_time": datetime(2026, 9, 10, 8, 30, tzinfo=timezone.utc),
        },
    ),
    (
        Report.Module.OPERATIONAL_PERFORMANCE,
        "Operational Performance Report",
        ("id", "name", "total_assets", "average_health_score"),
        {
            "id": "facility-101",
            "name": "Central Facility",
            "total_assets": 12,
            "average_health_score": Decimal("81.00"),
        },
    ),
)


def report_stub(module):
    return SimpleNamespace(
        module=module,
        parameters={
            "facility_id": "facility-101",
            "status": "open",
            "date_from": "2026-09-01",
            "date_to": "2026-09-30",
        },
        updated_at=datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc),
        created_by=SimpleNamespace(full_name="Operations Manager"),
    )


@pytest.mark.parametrize("module,title,columns,row", OPERATIONS_CASES)
def test_operations_pdf_uses_enterprise_layout_without_altering_data(
    module,
    title,
    columns,
    row,
):
    rows = [{**row, "description": row.get("description", "") + (" wrapped detail" * 12)}]
    rows.extend(
        {**row, columns[0]: f"row-marker-{index}"}
        for index in range(2, 58)
    )

    content = _render_operations_pdf(report_stub(module), title, columns, rows)
    reader = PdfReader(io.BytesIO(content))
    pages = [page.extract_text() or "" for page in reader.pages]
    full_text = "\n".join(pages)

    assert content.startswith(b"%PDF-")
    assert len(pages) > 1
    assert title in full_text
    assert "SFLMS Operations Report" in full_text
    assert "Records" in full_text
    assert str(next(iter(row.values()))) in full_text
    assert "2026-09-01 to 2026-09-30" in full_text
    assert all("SFLMS | Operations Report" in page for page in pages)
    assert all(f"Page {index}" in page for index, page in enumerate(pages, start=1))
    assert all(float(page.mediabox.width) > float(page.mediabox.height) for page in reader.pages)
    first_header_word = _operations_column_label(columns[0]).split()[0]
    assert all(first_header_word in page for page in pages if "row-marker" in page)
    if "health_score" in columns or "average_health_score" in columns:
        assert "81%" in full_text


@pytest.mark.parametrize("module,title,columns,row", OPERATIONS_CASES)
def test_operations_xlsx_keeps_report_sheet_data_and_green_formatting(
    module,
    title,
    columns,
    row,
):
    rendered_row = dict(row)
    if "description" in rendered_row:
        rendered_row["description"] = rendered_row["description"] + (" wrapped detail" * 8)
    content = _render_operations_xlsx(
        report_stub(module),
        title,
        columns,
        [rendered_row],
    )

    with zipfile.ZipFile(io.BytesIO(content)) as workbook:
        names = set(workbook.namelist())
        workbook_xml = workbook.read("xl/workbook.xml").decode("utf-8")
        worksheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        styles_xml = workbook.read("xl/styles.xml").decode("utf-8")
        worksheet = ElementTree.fromstring(worksheet_xml)

    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    assert {
        "xl/workbook.xml",
        "xl/styles.xml",
        "xl/worksheets/sheet1.xml",
    } <= names
    assert 'name="Report"' in workbook_xml
    assert title in worksheet_xml
    assert str(next(iter(row.values()))) in worksheet_xml
    assert "2026-09-01 to 2026-09-30" in worksheet_xml
    # The SFLMS report family accent is green and is defined once in
    # apps/reports/services.py, so this asserts the shared palette rather
    # than a colour literal duplicated in the test.
    assert _argb(REPORT_ACCENT) in styles_xml
    assert _argb(REPORT_ACCENT_LIGHT) in styles_xml
    assert _argb(REPORT_ACCENT_DARK) in styles_xml
    assert worksheet.find("x:sheetViews/x:sheetView", namespace).attrib["showGridLines"] == "0"
    pane = worksheet.find("x:sheetViews/x:sheetView/x:pane", namespace)
    assert pane.attrib["ySplit"] == "4"
    assert pane.attrib["state"] == "frozen"
    assert worksheet.find("x:autoFilter", namespace) is not None
    if "description" in columns:
        assert float(worksheet.find("x:sheetData/x:row[@r='5']", namespace).attrib["ht"]) > 22
    if "average_health_score" in columns:
        percentage_cell = worksheet.find("x:sheetData/x:row[@r='5']/x:c[@r='D5']", namespace)
        assert percentage_cell.attrib["s"] == "7"
        assert percentage_cell.find("x:v", namespace).text == "0.81"


def test_empty_operations_pdf_and_xlsx_keep_professional_structure():
    report = report_stub(Report.Module.MAINTENANCE)
    columns = ("asset_id", "description", "status")

    pdf = _render_operations_pdf(report, "Maintenance Report", columns, [])
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    assert "Maintenance Report" in pdf_text
    assert "Records" in pdf_text
    assert OPERATIONS_EMPTY_MESSAGE in pdf_text

    xlsx = _render_operations_xlsx(report, "Maintenance Report", columns, [])
    with zipfile.ZipFile(io.BytesIO(xlsx)) as workbook:
        worksheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        worksheet = ElementTree.fromstring(worksheet_xml)
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    assert OPERATIONS_EMPTY_MESSAGE in worksheet_xml
    assert "Asset ID" in worksheet_xml
    assert "Description" in worksheet_xml
    assert "Status" in worksheet_xml
    assert worksheet.find("x:sheetData/x:row[@r='4']", namespace) is not None
    assert worksheet.find("x:sheetData/x:row[@r='5']", namespace) is not None


def create_fault_report_asset(*, facility, actor, suffix):
    return Asset.objects.create(
        facility=facility,
        name=f"Report Asset {suffix}",
        asset_type="Mechanical",
        category="pump",
        serial_number=f"FAULT-REPORT-{suffix}",
        manufacturer="SFLMS",
        model="R1",
        location_inside_facility="Plant room",
        installation_date=date(2025, 1, 1),
        operation_date=date(2025, 1, 2),
        created_by=actor,
    )


def create_fault(*, asset, actor, marker, discovery_time, created_at):
    fault = Fault.objects.create(
        asset=asset,
        fault_type=marker,
        description=f"{marker} description",
        severity=Fault.Severity.MAJOR,
        discovery_time=discovery_time,
        reported_by=actor,
        created_by=actor,
    )
    Fault.objects.filter(pk=fault.pk).update(created_at=created_at)
    return fault


@pytest.fixture
def fault_report_records(role_operations_manager):
    actor = User.objects.create_user(
        email="fault-report-manager@sflms.test",
        username="fault-report-manager",
        full_name="Fault Report Manager",
        password="StrongPass123!",
        role=role_operations_manager,
    )
    facility = Facility.objects.create(
        name="Fault Report Facility",
        type=Facility.Type.INDUSTRIAL,
        location="Cairo",
        operation_start_date=date(2025, 1, 1),
        created_by=actor,
    )
    other_facility = Facility.objects.create(
        name="Other Fault Facility",
        type=Facility.Type.INDUSTRIAL,
        location="Giza",
        operation_start_date=date(2025, 1, 1),
        created_by=actor,
    )
    asset = create_fault_report_asset(
        facility=facility,
        actor=actor,
        suffix="VISIBLE",
    )
    other_asset = create_fault_report_asset(
        facility=other_facility,
        actor=actor,
        suffix="HIDDEN",
    )

    create_fault(
        asset=asset,
        actor=actor,
        marker="LOWER-BOUNDARY",
        discovery_time=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        created_at=datetime(2025, 11, 1, 0, 0, tzinfo=timezone.utc),
    )
    create_fault(
        asset=asset,
        actor=actor,
        marker="UPPER-BOUNDARY-UNRESOLVED",
        discovery_time=datetime(2026, 1, 31, 23, 59, tzinfo=timezone.utc),
        created_at=datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc),
    )
    create_fault(
        asset=asset,
        actor=actor,
        marker="OUTSIDE-DISCOVERY-RANGE",
        discovery_time=datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
    )
    create_fault(
        asset=other_asset,
        actor=actor,
        marker="OTHER-FACILITY",
        discovery_time=datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
    )
    return actor, facility


def fault_report(*, actor, facility, report_format):
    return create_report_request(
        report_type="Faults Report",
        module=Report.Module.FAULTS,
        report_format=report_format,
        parameters={
            "facility_id": str(facility.pk),
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "period_label": "January 2026",
        },
        actor=actor,
    )


@pytest.mark.django_db
def test_fault_report_rows_use_discovery_time_boundaries_and_facility_scope(
    fault_report_records,
):
    actor, facility = fault_report_records
    rows = build_domain_report_rows(
        fault_report(
            actor=actor,
            facility=facility,
            report_format=Report.Format.PDF,
        )
    )

    assert [row["fault_type"] for row in rows] == [
        "LOWER-BOUNDARY",
        "UPPER-BOUNDARY-UNRESOLVED",
    ]
    assert all("discovery_time" in row for row in rows)
    assert all("reported_date" not in row for row in rows)
    assert rows[1]["status"] == Fault.Status.REPORTED
    assert rows[1]["resolved_at"] is None


@pytest.mark.django_db
def test_real_fault_data_completes_pdf_and_xlsx_generation(fault_report_records):
    actor, facility = fault_report_records
    generated_reports = []
    try:
        pdf = generate_report(
            report_id=fault_report(
                actor=actor,
                facility=facility,
                report_format=Report.Format.PDF,
            ).pk
        )
        generated_reports.append(pdf)
        with pdf.file_path.open("rb") as output:
            pdf_text = " ".join(
                "\n".join(
                    page.extract_text() or ""
                    for page in PdfReader(io.BytesIO(output.read())).pages
                ).split()
            )
        assert pdf.status == Report.Status.COMPLETED
        assert "LOWER-BOUNDARY" in pdf_text
        assert "UPPER-BOUNDARY-UNRESOLVED" in pdf_text
        assert "OUTSIDE-DISCOVERY-RANGE" not in pdf_text
        assert "OTHER-FACILITY" not in pdf_text

        xlsx = generate_report(
            report_id=fault_report(
                actor=actor,
                facility=facility,
                report_format=Report.Format.EXCEL,
            ).pk
        )
        generated_reports.append(xlsx)
        with xlsx.file_path.open("rb") as output:
            with zipfile.ZipFile(io.BytesIO(output.read())) as workbook:
                worksheet_xml = workbook.read(
                    "xl/worksheets/sheet1.xml"
                ).decode("utf-8")
        assert xlsx.status == Report.Status.COMPLETED
        assert "LOWER-BOUNDARY" in worksheet_xml
        assert "UPPER-BOUNDARY-UNRESOLVED" in worksheet_xml
        assert "OUTSIDE-DISCOVERY-RANGE" not in worksheet_xml
        assert "OTHER-FACILITY" not in worksheet_xml
    finally:
        for generated in generated_reports:
            name = generated.file_path.name
            generated.file_path.close()
            if name and generated.file_path.storage.exists(name):
                generated.file_path.storage.delete(name)


# ---------------------------------------------------------------------------
# Report family coverage
#
# Regression: projects/materials/security/users/alerts/response reports fell
# through to an unstyled generator that emitted latin-1 encoded plain text for
# PDF and a style-less sheet for XLSX. They now render with the same structure
# and green accent as every other SFLMS report.
# ---------------------------------------------------------------------------

FAMILY_MODULES = (
    Report.Module.PROJECTS,
    Report.Module.MATERIALS,
    Report.Module.SECURITY,
    Report.Module.USERS,
    Report.Module.ALERTS,
    Report.Module.RESPONSE,
)


@pytest.mark.parametrize("module", FAMILY_MODULES)
def test_every_module_pdf_uses_the_shared_report_structure(module):
    title = f"{module.label} Report"
    columns = ("id", "name", "status")
    rows = [{"id": "row-1", "name": "Sample record", "status": "open"}]

    content = _render_operations_pdf(report_stub(module), title, columns, rows)
    reader = PdfReader(io.BytesIO(content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert content.startswith(b"%PDF-")
    # Same page frame, header band and footer as the rest of the family.
    assert title in text
    assert "SFLMS Operations Report" in text
    assert "Records" in text
    assert "row-1" in text and "Sample record" in text
    assert all("SFLMS | Operations Report" in (page.extract_text() or "") for page in reader.pages)
    assert all(float(page.mediabox.width) > float(page.mediabox.height) for page in reader.pages)


@pytest.mark.parametrize("module", FAMILY_MODULES)
def test_every_module_xlsx_is_styled_with_the_green_accent(module):
    title = f"{module.label} Report"
    columns = ("id", "name", "status")
    rows = [{"id": "row-1", "name": "Sample record", "status": "open"}]

    content = _render_operations_xlsx(report_stub(module), title, columns, rows)
    with zipfile.ZipFile(io.BytesIO(content)) as workbook:
        names = set(workbook.namelist())
        styles_xml = workbook.read("xl/styles.xml").decode("utf-8")
        worksheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")

    # A styles part is what the old generic writer never produced.
    assert "xl/styles.xml" in names
    assert _argb(REPORT_ACCENT) in styles_xml
    assert _argb(REPORT_ACCENT_DARK) in styles_xml
    assert title in worksheet_xml
    assert "row-1" in worksheet_xml and "Sample record" in worksheet_xml
    # Column widths and a frozen header are part of the family's sheet setup.
    assert "<cols>" in worksheet_xml
    assert "pane" in worksheet_xml


def test_pdf_and_xlsx_share_title_metadata_and_data():
    """The two formats must represent the same report."""

    module = Report.Module.PROJECTS
    title = "Projects Report"
    columns = ("id", "name", "status")
    rows = [{"id": "row-1", "name": "Sample record", "status": "open"}]
    stub = report_stub(module)

    pdf = _render_operations_pdf(stub, title, columns, rows)
    xlsx = _render_operations_xlsx(stub, title, columns, rows)

    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    with zipfile.ZipFile(io.BytesIO(xlsx)) as workbook:
        sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")

    for token in (title, "row-1", "Sample record", "2026-09-01 to 2026-09-30"):
        assert token in pdf_text, token
        assert token in sheet, token


def test_arabic_survives_the_report_pipeline():
    """The replaced generator encoded latin-1 and destroyed Arabic text."""

    module = Report.Module.SECURITY
    columns = ("id", "name")
    rows = [{"id": "row-1", "name": "تقرير الأمن"}]

    xlsx = _render_operations_xlsx(report_stub(module), "Security Report", columns, rows)
    with zipfile.ZipFile(io.BytesIO(xlsx)) as workbook:
        sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "تقرير الأمن" in sheet

    pdf = _render_operations_pdf(report_stub(module), "Security Report", columns, rows)
    assert pdf.startswith(b"%PDF-")
    assert b"?" * 8 not in pdf


def test_id_column_is_labelled_per_module():
    """`id` means a facility only in the operations modules."""

    assert _operations_column_label("id", Report.Module.OPERATIONAL_PERFORMANCE) == "Facility ID"
    assert _operations_column_label("id", Report.Module.ASSETS) == "Facility ID"
    for module in FAMILY_MODULES:
        assert _operations_column_label("id", module) == "ID", module
    # An explicit facility column keeps its label everywhere.
    assert _operations_column_label("facility_id", Report.Module.USERS) == "Facility ID"


def test_users_report_header_does_not_claim_a_facility_id():
    columns = ("id", "full_name")
    rows = [{"id": "u-1", "full_name": "Ops Manager"}]
    xlsx = _render_operations_xlsx(report_stub(Report.Module.USERS), "Users Report", columns, rows)
    with zipfile.ZipFile(io.BytesIO(xlsx)) as workbook:
        sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "Facility ID" not in sheet
