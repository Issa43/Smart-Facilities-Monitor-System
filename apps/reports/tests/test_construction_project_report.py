import io
import zipfile
from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch
from xml.etree import ElementTree

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from pypdf import PdfReader

from apps.construction.models import DailyReport, QualityInspection, SitePhoto
from apps.materials.models import Material, MaterialRequest
from apps.projects.models import (
    PhaseProgressLog,
    Project,
    ProjectAssignment,
    ProjectDocument,
    ProjectPhase,
)
from apps.reports.models import Report
from apps.reports.services import (
    CONSTRUCTION_EMPTY_MESSAGE,
    build_construction_report_dataset,
    create_report_request,
    generate_report,
)
from apps.reports.tasks import generate_report_task
from apps.users.models import User


REPORT_DATE_FROM = "2026-01-01"
REPORT_DATE_TO = "2026-01-31"
IN_RANGE_TIME = datetime(2026, 1, 15, 12, 0, tzinfo=datetime_timezone.utc)
OUT_OF_RANGE_TIME = datetime(2025, 12, 15, 12, 0, tzinfo=datetime_timezone.utc)
PDF_BYTES = b"%PDF-1.4\n%%EOF\n"


def png_upload(name):
    content = io.BytesIO()
    Image.new("RGB", (2, 2), color="white").save(content, format="PNG")
    return SimpleUploadedFile(name, content.getvalue(), content_type="image/png")


def extract_pdf_pages(content):
    return [page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages]


def extract_pdf_text(content):
    return " ".join("\n".join(extract_pdf_pages(content)).split())


@pytest.fixture(autouse=True)
def clean_generated_domain_files():
    yield
    for document in ProjectDocument.all_objects.all():
        if document.file and document.file.storage.exists(document.file.name):
            document.file.storage.delete(document.file.name)
    for photo in SitePhoto.all_objects.all():
        if photo.image and photo.image.storage.exists(photo.image.name):
            photo.image.storage.delete(photo.image.name)


def create_manager(role, suffix):
    return User.objects.create_user(
        email=f"{suffix}@sflms.test",
        username=suffix,
        full_name=suffix.replace("-", " ").title(),
        password="StrongPass123!",
        role=role,
    )


def create_project(*, actor, manager, suffix):
    project = Project.objects.create(
        name=f"Project {suffix}",
        facility_type=Project.FacilityType.COMMERCIAL,
        description=f"Construction scope {suffix}",
        location=f"Location {suffix}",
        start_date=date(2025, 12, 1),
        expected_completion_date=date(2026, 12, 31),
        status=Project.Status.IN_PROGRESS,
        created_by=actor,
    )
    assignment = ProjectAssignment.objects.create(
        project=project,
        user=manager,
        role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
        created_by=actor,
    )
    return project, assignment


def create_report(*, actor, project, report_format):
    return create_report_request(
        report_type="Construction Project Report",
        module=Report.Module.CONSTRUCTION,
        report_format=report_format,
        parameters={
            "project_id": str(project.pk),
            "date_from": REPORT_DATE_FROM,
            "date_to": REPORT_DATE_TO,
            "period_label": "January 2026",
        },
        actor=actor,
    )


def populate_project(*, project, actor, marker):
    phase = ProjectPhase.objects.create(
        project=project,
        name=f"{marker} Phase",
        description="Foundation execution",
        sequence_number=1,
        start_date=date(2025, 12, 1),
        expected_completion_date=date(2026, 3, 31),
        actual_start_date=date(2025, 12, 2),
        initial_progress=Decimal("5.00"),
        current_progress=Decimal("40.00"),
        priority=ProjectPhase.Priority.HIGH,
        status=ProjectPhase.Status.IN_PROGRESS,
        created_by=actor,
    )
    progress = PhaseProgressLog.objects.create(
        phase=phase,
        progress_percentage=Decimal("40.00"),
        work_completed=f"{marker} progress work",
        notes=f"{marker} progress notes",
        created_by=actor,
    )
    PhaseProgressLog.all_objects.filter(pk=progress.pk).update(
        created_at=IN_RANGE_TIME
    )
    old_progress = PhaseProgressLog.objects.create(
        phase=phase,
        progress_percentage=Decimal("20.00"),
        work_completed=f"{marker} old progress",
        notes="Outside range",
        created_by=actor,
    )
    PhaseProgressLog.all_objects.filter(pk=old_progress.pk).update(
        created_at=OUT_OF_RANGE_TIME
    )

    DailyReport.objects.create(
        project=project,
        phase=phase,
        report_date=date(2026, 1, 14),
        title=f"{marker} Daily Report",
        progress_percentage=Decimal("40.00"),
        weather_condition="Clear",
        workers_count=18,
        equipment_used=["Crane"],
        report_content=f"{marker} completed concrete work",
        issues=f"{marker} no blocking issues",
        created_by=actor,
    )
    DailyReport.objects.create(
        project=project,
        phase=phase,
        report_date=date(2025, 12, 14),
        title=f"{marker} Old Daily Report",
        progress_percentage=Decimal("20.00"),
        weather_condition="Clear",
        workers_count=10,
        equipment_used=[],
        report_content=f"{marker} outside-range daily work",
        issues="",
        created_by=actor,
    )

    material = Material.objects.create(
        project=project,
        name=f"{marker} Steel",
        unit=Material.Unit.KILOGRAM,
        quantity_required=Decimal("100.000"),
        quantity_used=Decimal("40.000"),
        quantity_remaining=Decimal("60.000"),
        min_stock_threshold=Decimal("20.000"),
        created_by=actor,
    )
    MaterialRequest.objects.create(
        project=project,
        material=material,
        quantity_requested=Decimal("10.000"),
        reason=f"{marker} reinforcement",
        priority=MaterialRequest.Priority.HIGH,
        status=MaterialRequest.Status.APPROVED,
        created_by=actor,
    )

    QualityInspection.objects.create(
        project=project,
        phase=phase,
        title=f"{marker} Quality Inspection",
        inspector=actor,
        score=Decimal("92.00"),
        result=QualityInspection.Result.PASSED,
        notes=f"{marker} quality notes",
        inspected_at=IN_RANGE_TIME,
        created_by=actor,
    )
    QualityInspection.objects.create(
        project=project,
        phase=phase,
        title=f"{marker} Old Inspection",
        inspector=actor,
        score=Decimal("50.00"),
        result=QualityInspection.Result.FAILED,
        notes="Outside range",
        inspected_at=OUT_OF_RANGE_TIME,
        created_by=actor,
    )

    document = ProjectDocument.objects.create(
        project=project,
        document_type="drawing",
        title=f"{marker} Drawing",
        file=SimpleUploadedFile(
            f"{marker.lower()}-drawing.pdf",
            PDF_BYTES,
            content_type="application/pdf",
        ),
        created_by=actor,
    )
    ProjectDocument.all_objects.filter(pk=document.pk).update(
        created_at=IN_RANGE_TIME
    )
    old_document = ProjectDocument.objects.create(
        project=project,
        document_type="drawing",
        title=f"{marker} Old Drawing",
        file=SimpleUploadedFile(
            f"{marker.lower()}-old.pdf",
            PDF_BYTES,
            content_type="application/pdf",
        ),
        created_by=actor,
    )
    ProjectDocument.all_objects.filter(pk=old_document.pk).update(
        created_at=OUT_OF_RANGE_TIME
    )

    SitePhoto.objects.create(
        project=project,
        phase=phase,
        image=png_upload(f"{marker.lower()}.png"),
        caption=f"{marker} Site Photo",
        captured_at=IN_RANGE_TIME,
        created_by=actor,
    )
    SitePhoto.objects.create(
        project=project,
        phase=phase,
        image=png_upload(f"{marker.lower()}-old.png"),
        caption=f"{marker} Old Site Photo",
        captured_at=OUT_OF_RANGE_TIME,
        created_by=actor,
    )
    return phase


def section_map(dataset):
    return {section["key"]: section for section in dataset["sections"]}


@pytest.mark.django_db
def test_construction_dataset_is_scoped_and_applies_date_semantics(
    role_construction_manager,
    super_admin_user,
):
    manager = create_manager(role_construction_manager, "contract-manager")
    project, _ = create_project(
        actor=super_admin_user,
        manager=manager,
        suffix="Included",
    )
    other_project, _ = create_project(
        actor=super_admin_user,
        manager=manager,
        suffix="Excluded",
    )
    populate_project(project=project, actor=manager, marker="INCLUDED")
    populate_project(project=other_project, actor=manager, marker="EXCLUDED")

    dataset = build_construction_report_dataset(
        create_report(actor=manager, project=project, report_format=Report.Format.PDF)
    )
    sections = section_map(dataset)

    assert dataset["project"]["name"] == "Project Included"
    assert dataset["metadata"]["period"] == "January 2026"
    assert [section["sheet_name"] for section in dataset["sections"]] == [
        "Phases",
        "Progress",
        "Daily Reports",
        "Materials",
        "Material Requests",
        "Quality",
        "Documents",
        "Photos",
    ]
    assert len(sections["phases"]["rows"]) == 1
    assert len(sections["materials"]["rows"]) == 1
    assert len(sections["material_requests"]["rows"]) == 1
    assert len(sections["progress"]["rows"]) == 1
    assert len(sections["daily_reports"]["rows"]) == 1
    assert len(sections["quality"]["rows"]) == 1
    assert len(sections["documents"]["rows"]) == 1
    assert len(sections["photos"]["rows"]) == 1
    assert sections["daily_reports"]["rows"][0]["title"] == "INCLUDED Daily Report"
    assert sections["documents"]["rows"][0] == {
        "title": "INCLUDED Drawing",
        "document_type": "drawing",
        "original_file_name": "included-drawing.pdf",
        "mime_type": "application/pdf",
        "file_size": len(PDF_BYTES),
        "uploader_name": manager.full_name,
        "uploaded_at": IN_RANGE_TIME,
    }
    assert "file" not in sections["documents"]["rows"][0]
    assert "image" not in sections["photos"]["rows"][0]
    assert dataset["summary"] == {
        "phase_count": 1,
        "progress_count": 1,
        "daily_report_count": 1,
        "material_count": 1,
        "material_request_count": 1,
        "open_material_request_count": 1,
        "quality_count": 1,
        "failed_inspection_count": 0,
        "document_count": 1,
        "photo_count": 1,
    }
    assert "EXCLUDED" not in repr(dataset)
    assert "outside-range" not in repr(dataset)

    all_history_report = create_report_request(
        report_type="Construction Project Report",
        module=Report.Module.CONSTRUCTION,
        report_format=Report.Format.PDF,
        parameters={"project_id": str(project.pk)},
        actor=manager,
    )
    all_history = build_construction_report_dataset(
        all_history_report,
        daily_columns=["report_date", "title"],
    )
    all_history_sections = section_map(all_history)
    assert len(all_history_sections["progress"]["rows"]) == 2
    assert len(all_history_sections["daily_reports"]["rows"]) == 2
    assert len(all_history_sections["quality"]["rows"]) == 2
    assert len(all_history_sections["documents"]["rows"]) == 2
    assert len(all_history_sections["photos"]["rows"]) == 2
    assert all_history_sections["daily_reports"]["columns"] == (
        ("report_date", "Report Date"),
        ("title", "Title"),
    )
    assert len(all_history_sections["phases"]["columns"]) > 2


@pytest.mark.django_db
def test_construction_generation_revalidates_assignment(
    role_construction_manager,
    super_admin_user,
):
    manager = create_manager(role_construction_manager, "revoked-manager")
    project, assignment = create_project(
        actor=super_admin_user,
        manager=manager,
        suffix="Revoked",
    )
    report = create_report(
        actor=manager,
        project=project,
        report_format=Report.Format.PDF,
    )
    assignment.soft_delete()

    with pytest.raises(ValidationError, match="no longer assigned"):
        generate_report(report_id=report.pk)

    report.refresh_from_db()
    assert report.status == Report.Status.FAILED
    assert "no longer assigned" in report.parameters["_generation_error"]


@pytest.mark.django_db
def test_construction_pdf_and_xlsx_contain_all_sections_and_project_data(
    role_construction_manager,
    super_admin_user,
):
    manager = create_manager(role_construction_manager, "render-manager")
    project, _ = create_project(
        actor=super_admin_user,
        manager=manager,
        suffix="Rendered",
    )
    other_project, _ = create_project(
        actor=super_admin_user,
        manager=manager,
        suffix="Hidden",
    )
    populate_project(project=project, actor=manager, marker="VISIBLE")
    populate_project(project=other_project, actor=manager, marker="HIDDEN")
    generated = []
    try:
        pdf = generate_report(
            report_id=create_report(
                actor=manager,
                project=project,
                report_format=Report.Format.PDF,
            ).pk
        )
        generated.append(pdf)
        pdf_content = extract_pdf_text(pdf.file_path.open("rb").read())
        for expected in (
            "Project Overview",
            "Summary",
            "Phases",
            "Progress",
            "Daily Reports",
            "Materials",
            "Material Requests",
            "Quality",
            "Documents",
            "Photos",
            "VISIBLE Daily Report",
            "VISIBLE Steel",
            "VISIBLE Quality Inspection",
        ):
            assert expected in pdf_content
        assert "HIDDEN" not in pdf_content
        assert "outside-range" not in pdf_content

        xlsx = generate_report(
            report_id=create_report(
                actor=manager,
                project=project,
                report_format=Report.Format.EXCEL,
            ).pk
        )
        generated.append(xlsx)
        with zipfile.ZipFile(io.BytesIO(xlsx.file_path.open("rb").read())) as workbook:
            workbook_xml = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
            namespace = {
                "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            }
            assert [
                sheet.attrib["name"]
                for sheet in workbook_xml.findall("x:sheets/x:sheet", namespace)
            ] == [
                "Summary",
                "Phases",
                "Progress",
                "Daily Reports",
                "Materials",
                "Material Requests",
                "Quality",
                "Documents",
                "Photos",
            ]
            workbook_text = "\n".join(
                workbook.read(f"xl/worksheets/sheet{index}.xml").decode("utf-8")
                for index in range(1, 10)
            )
            expected_headers = {
                2: "Sequence",
                3: "Work Completed",
                4: "Workforce Count",
                5: "Quantity Remaining",
                6: "Quantity Requested",
                7: "Inspector",
                8: "Original Filename",
                9: "Captured At",
            }
            for sheet_number, header in expected_headers.items():
                assert header in workbook.read(
                    f"xl/worksheets/sheet{sheet_number}.xml"
                ).decode("utf-8")
            styles_xml = workbook.read("xl/styles.xml").decode("utf-8")
            assert 'formatCode="yyyy-mm-dd"' in styles_xml
            assert 'formatCode="yyyy-mm-dd hh:mm"' in styles_xml
            assert 'formatCode="0%"' in styles_xml
            for sheet_number in range(1, 10):
                sheet_root = ElementTree.fromstring(
                    workbook.read(f"xl/worksheets/sheet{sheet_number}.xml")
                )
                pane = sheet_root.find("x:sheetViews/x:sheetView/x:pane", namespace)
                assert pane is not None
                assert pane.attrib["state"] == "frozen"
                assert pane.attrib["ySplit"] == "4"
                widths = [
                    float(column.attrib["width"])
                    for column in sheet_root.findall("x:cols/x:col", namespace)
                ]
                assert widths
                assert all(12 <= width <= 42 for width in widths)
                header_row = sheet_root.find("x:sheetData/x:row[@r='4']", namespace)
                assert header_row is not None
                assert all(
                    cell.attrib.get("s") == "3"
                    for cell in header_row.findall("x:c", namespace)
                )

            phase_sheet = workbook.read("xl/worksheets/sheet2.xml").decode("utf-8")
            quality_sheet = workbook.read("xl/worksheets/sheet7.xml").decode("utf-8")
            daily_sheet = workbook.read("xl/worksheets/sheet4.xml").decode("utf-8")
            assert "VISIBLE Phase" in phase_sheet
            assert "VISIBLE Quality Inspection" not in phase_sheet
            assert "VISIBLE Quality Inspection" in quality_sheet
            assert "VISIBLE Daily Report" in daily_sheet
            assert 's="7" t="n"><v>0.4</v>' in phase_sheet
        for expected in (
            "Project Rendered",
            "VISIBLE Daily Report",
            "VISIBLE Steel",
            "VISIBLE Quality Inspection",
            "VISIBLE Drawing",
            "VISIBLE Site Photo",
        ):
            assert expected in workbook_text
        assert "HIDDEN" not in workbook_text
        assert "outside-range" not in workbook_text
    finally:
        for report in generated:
            report.file_path.storage.delete(report.file_path.name)


@pytest.mark.django_db
@pytest.mark.parametrize("report_format", [Report.Format.PDF, Report.Format.EXCEL])
def test_async_task_exports_existing_project_phases_and_quality(
    role_construction_manager,
    super_admin_user,
    report_format,
):
    manager = create_manager(role_construction_manager, f"task-{report_format}")
    project, _ = create_project(
        actor=super_admin_user,
        manager=manager,
        suffix=f"Task {report_format}",
    )
    populate_project(project=project, actor=manager, marker="ASYNC VISIBLE")
    report = create_report(
        actor=manager,
        project=project,
        report_format=report_format,
    )

    try:
        with patch("apps.reports.tasks.notify_user"):
            generate_report_task.run(str(report.pk))

        report.refresh_from_db()
        assert report.status == Report.Status.COMPLETED
        content = report.file_path.open("rb").read()
        if report_format == Report.Format.PDF:
            exported_text = extract_pdf_text(content)
        else:
            with zipfile.ZipFile(io.BytesIO(content)) as workbook:
                exported_text = "\n".join(
                    workbook.read(f"xl/worksheets/sheet{index}.xml").decode("utf-8")
                    for index in range(1, 10)
                )

        assert "ASYNC VISIBLE Phase" in exported_text
        assert "ASYNC VISIBLE Quality Inspection" in exported_text
    finally:
        if report.file_path:
            report.file_path.storage.delete(report.file_path.name)


@pytest.mark.django_db
def test_construction_pdf_uses_a4_layout_repeated_headers_and_unicode_period(
    role_construction_manager,
    super_admin_user,
):
    manager = create_manager(role_construction_manager, "pdf-layout-manager")
    project, _ = create_project(
        actor=super_admin_user,
        manager=manager,
        suffix="PDF Layout",
    )
    populate_project(project=project, actor=manager, marker="LAYOUT VISIBLE")
    for sequence in range(2, 62):
        ProjectPhase.objects.create(
            project=project,
            name=f"Pagination Phase {sequence} with wrapped enterprise detail",
            description="Long phase content used to verify clean table pagination.",
            sequence_number=sequence,
            start_date=date(2026, 1, 1),
            expected_completion_date=date(2026, 6, 30),
            initial_progress=Decimal("0.00"),
            current_progress=Decimal("81.00"),
            priority=ProjectPhase.Priority.MEDIUM,
            status=ProjectPhase.Status.IN_PROGRESS,
            created_by=manager,
        )
    report = create_report(
        actor=manager,
        project=project,
        report_format=Report.Format.PDF,
    )
    report.parameters["period_label"] = "آخر 30 يوماً"
    report.save(update_fields=["parameters", "updated_at"])

    generated = None
    try:
        generated = generate_report(report_id=report.pk)
        content = generated.file_path.open("rb").read()
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]

        assert len(pages) > 1
        for page_number, (page, text) in enumerate(zip(reader.pages, pages), start=1):
            assert float(page.mediabox.width) > float(page.mediabox.height)
            assert round(float(page.mediabox.width)) == 842
            assert round(float(page.mediabox.height)) == 595
            assert "SFLMS | Construction Project Report" in text
            assert f"Page {page_number}" in text

        full_text = "\n".join(pages)
        assert "Construction Project Report" in full_text
        assert "Project Overview" in full_text
        assert "81%" in full_text
        assert "??? 30" not in full_text
        phase_pages = [
            text for text in pages if "Pagination Phase" in " ".join(text.split())
        ]
        assert len(phase_pages) > 1
        assert all("Sequence" in " ".join(text.split()) for text in phase_pages)
    finally:
        if generated and generated.file_path:
            generated.file_path.storage.delete(generated.file_path.name)


@pytest.mark.django_db
def test_empty_construction_sections_are_explicit_in_pdf_and_xlsx(
    role_construction_manager,
    super_admin_user,
):
    manager = create_manager(role_construction_manager, "empty-manager")
    project, _ = create_project(
        actor=super_admin_user,
        manager=manager,
        suffix="Empty",
    )
    generated = []
    try:
        pdf = generate_report(
            report_id=create_report(
                actor=manager,
                project=project,
                report_format=Report.Format.PDF,
            ).pk
        )
        generated.append(pdf)
        pdf_content = extract_pdf_text(pdf.file_path.open("rb").read())
        assert "Project Empty" in pdf_content
        assert pdf_content.count(CONSTRUCTION_EMPTY_MESSAGE) == 8

        xlsx = generate_report(
            report_id=create_report(
                actor=manager,
                project=project,
                report_format=Report.Format.EXCEL,
            ).pk
        )
        generated.append(xlsx)
        with zipfile.ZipFile(io.BytesIO(xlsx.file_path.open("rb").read())) as workbook:
            namespace = {
                "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            }
            empty_sheets = []
            for index in range(2, 10):
                sheet_xml = workbook.read(f"xl/worksheets/sheet{index}.xml").decode(
                    "utf-8"
                )
                empty_sheets.append(sheet_xml.count(CONSTRUCTION_EMPTY_MESSAGE))
                sheet_root = ElementTree.fromstring(sheet_xml)
                assert sheet_root.find(
                    "x:sheetData/x:row[@r='4']", namespace
                ) is not None
                empty_row = sheet_root.find("x:sheetData/x:row[@r='5']", namespace)
                assert empty_row is not None
                assert empty_row.find("x:c", namespace).attrib["s"] == "10"
                assert sheet_root.find("x:mergeCells", namespace) is not None
                assert sheet_root.find(
                    "x:sheetViews/x:sheetView/x:pane", namespace
                ).attrib["ySplit"] == "4"
            daily_sheet = workbook.read("xl/worksheets/sheet4.xml").decode("utf-8")
        assert empty_sheets == [1] * 8
        assert "Report Date" in daily_sheet
        assert "Summary" in daily_sheet
    finally:
        for report in generated:
            report.file_path.storage.delete(report.file_path.name)
