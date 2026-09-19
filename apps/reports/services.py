import io
import json
import math
import textwrap
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from html import escape
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction

from .models import Report, ReportTemplate, validate_report_file


MAX_PARAMETER_BYTES = 64 * 1024
MAX_REPORT_ROWS = 10_000
MAX_REPORT_COLUMNS = 100
TEMPLATE_CONFIGURATION_KEYS = {"title", "columns", "default_parameters"}
DOMAIN_REPORT_COLUMNS = {
    Report.Module.PROJECTS: (
        "name", "facility_type", "location", "start_date",
        "expected_completion_date", "actual_completion_date", "status",
    ),
    Report.Module.CONSTRUCTION: (
        "project_id", "phase_id", "report_date", "weather_condition",
        "workers_count", "report_content", "issues",
    ),
    Report.Module.MATERIALS: (
        "project_id", "name", "unit", "quantity_required", "quantity_used",
        "quantity_remaining", "min_stock_threshold",
    ),
    Report.Module.ASSETS: (
        "facility_id", "name", "asset_type", "category", "serial_number",
        "current_status", "health_score", "remaining_useful_life",
    ),
    Report.Module.MAINTENANCE: (
        "asset_id", "type", "priority", "description", "reason",
        "expected_execution_date", "actual_completion_date", "status",
    ),
    Report.Module.FAULTS: (
        "asset_id", "asset__facility_id", "fault_type", "description",
        "severity", "status", "root_cause", "resolution", "discovery_time",
        "resolved_at",
    ),
    Report.Module.OPERATIONAL_PERFORMANCE: (
        "id", "name", "location", "total_assets", "operational_assets",
        "maintenance_assets", "out_of_service_assets", "average_health_score",
    ),
    Report.Module.SECURITY: (
        "incident_number", "facility_id", "incident_type", "description",
        "location", "severity_level", "status", "closed_at",
    ),
    Report.Module.USERS: (
        "full_name", "email", "username", "role__name", "status",
        "last_login", "created_at",
    ),
    Report.Module.ALERTS: (
        "facility_id", "alert_type", "location", "severity_level", "source",
        "status", "is_false_positive", "created_at",
    ),
    Report.Module.RESPONSE: (
        "incident__incident_number", "action_taken", "notes", "taken_by_id",
        "taken_at", "completed_at",
    ),
}

CONSTRUCTION_EMPTY_MESSAGE = "No records matched the selected project and period."

# Shared SFLMS report palette.
#
# The Construction Manager report defines the visual structure of the report
# family — page frame, header block, metadata grid, section headings, table
# style, summary block and footer. Every module renders with that structure and
# with this one green accent, so a PDF and an XLSX of any report read as the
# same document. Keeping the palette here means the accent is changed in one
# place rather than in four renderers.
REPORT_ACCENT_DARK = "#14532D"      # title band, section headings
REPORT_ACCENT = "#1B7A44"           # table headers, rules
REPORT_ACCENT_LIGHT = "#EAF4EE"     # metadata / summary panels
REPORT_ACCENT_LIGHTER = "#F5FAF7"   # zebra striping
REPORT_ACCENT_ON_DARK = "#E6F2EA"   # subtitle text on the accent band
REPORT_BORDER = "#C3DCCB"           # table grid and panel outlines
REPORT_BORDER_STRONG = "#AFCCBA"    # panel boxes
REPORT_TEXT = "#22312A"             # body copy (neutral, not green)
REPORT_MUTED = "#5F6F66"            # captions, footer


def _argb(hex_color):
    """``#RRGGBB`` to the ``FFRRGGBB`` form SpreadsheetML expects."""

    return "FF" + hex_color.lstrip("#").upper()


OPERATIONS_REPORT_MODULES = {
    Report.Module.ASSETS,
    Report.Module.MAINTENANCE,
    Report.Module.FAULTS,
    Report.Module.OPERATIONAL_PERFORMANCE,
}
OPERATIONS_EMPTY_MESSAGE = "No records matched the report parameters."
OPERATIONS_COLUMN_LABELS = {
    "id": "Facility ID",
    "facility_id": "Facility ID",
    "asset_id": "Asset ID",
    "asset__facility_id": "Facility ID",
    "asset_type": "Asset Type",
    "serial_number": "Serial Number",
    "current_status": "Current Status",
    "health_score": "Health Score",
    "remaining_useful_life": "Remaining Useful Life",
    "expected_execution_date": "Expected Execution Date",
    "actual_completion_date": "Actual Completion Date",
    "fault_type": "Fault Type",
    "root_cause": "Root Cause",
    "discovery_time": "Discovery Time",
    "resolved_at": "Resolved At",
    "total_assets": "Total Assets",
    "operational_assets": "Operational Assets",
    "maintenance_assets": "Under Maintenance",
    "out_of_service_assets": "Out of Service",
    "average_health_score": "Average Health Score",
}
CONSTRUCTION_DAILY_COLUMN_LABELS = {
    "project_id": "Project ID",
    "phase_id": "Phase ID",
    "report_date": "Report Date",
    "phase_name": "Phase",
    "title": "Title",
    "report_content": "Summary",
    "progress_percentage": "Progress Percentage",
    "workers_count": "Workforce Count",
    "weather_condition": "Weather Condition",
    "equipment_used": "Equipment Used",
    "issues": "Issues",
    "author_name": "Author",
}
CONSTRUCTION_REPORT_SECTIONS = (
    (
        "phases",
        "Phases",
        (
            ("sequence_number", "Sequence"),
            ("name", "Name"),
            ("priority", "Priority"),
            ("status", "Status"),
            ("start_date", "Start Date"),
            ("expected_completion_date", "Expected Completion Date"),
            ("actual_start_date", "Actual Start Date"),
            ("actual_completion_date", "Actual Completion Date"),
            ("current_progress", "Current Progress"),
            ("approval_status", "Approval Status"),
        ),
    ),
    (
        "progress",
        "Progress",
        (
            ("phase_name", "Phase"),
            ("progress_percentage", "Progress Percentage"),
            ("work_completed", "Work Completed"),
            ("notes", "Notes"),
            ("author_name", "Author"),
            ("recorded_at", "Recorded At"),
        ),
    ),
    (
        "daily_reports",
        "Daily Reports",
        tuple(
            (key, label)
            for key, label in CONSTRUCTION_DAILY_COLUMN_LABELS.items()
            if key not in {"project_id", "phase_id"}
        ),
    ),
    (
        "materials",
        "Materials",
        (
            ("name", "Name"),
            ("unit", "Unit"),
            ("quantity_required", "Quantity Required"),
            ("quantity_used", "Quantity Used"),
            ("quantity_remaining", "Quantity Remaining"),
            ("min_stock_threshold", "Minimum Stock Threshold"),
            ("low_stock", "Low Stock"),
        ),
    ),
    (
        "material_requests",
        "Material Requests",
        (
            ("material_name", "Material"),
            ("quantity_requested", "Quantity Requested"),
            ("unit", "Unit"),
            ("reason", "Reason"),
            ("priority", "Priority"),
            ("status", "Status"),
            ("requester_name", "Requester"),
            ("created_at", "Created At"),
            ("updated_at", "Updated At"),
        ),
    ),
    (
        "quality",
        "Quality",
        (
            ("phase_name", "Phase"),
            ("title", "Title"),
            ("inspector_name", "Inspector"),
            ("score", "Score"),
            ("result", "Result"),
            ("notes", "Notes"),
            ("inspected_at", "Inspected At"),
        ),
    ),
    (
        "documents",
        "Documents",
        (
            ("title", "Title"),
            ("document_type", "Document Type"),
            ("original_file_name", "Original Filename"),
            ("mime_type", "MIME Type"),
            ("file_size", "File Size"),
            ("uploader_name", "Uploader"),
            ("uploaded_at", "Uploaded At"),
        ),
    ),
    (
        "photos",
        "Photos",
        (
            ("caption", "Caption"),
            ("phase_name", "Phase"),
            ("original_file_name", "Original Filename"),
            ("mime_type", "MIME Type"),
            ("file_size", "File Size"),
            ("captured_at", "Captured At"),
        ),
    ),
)


def _require_active_actor(actor):
    if actor is None or not getattr(actor, "pk", None):
        raise ValidationError({"actor": "An authenticated actor is required."})
    if not actor.is_active:
        raise ValidationError({"actor": "The actor must be active."})


def _validate_json_object(value, field_name):
    if not isinstance(value, dict):
        raise ValidationError({field_name: "A JSON object is required."})
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            {field_name: "The value must contain only JSON-compatible data."}
        ) from exc
    if len(encoded.encode("utf-8")) > MAX_PARAMETER_BYTES:
        raise ValidationError(
            {field_name: "The JSON configuration exceeds the allowed size."}
        )
    return dict(value)


def validate_template_configuration(configuration):
    configuration = _validate_json_object(configuration, "configuration")
    unknown_keys = set(configuration) - TEMPLATE_CONFIGURATION_KEYS
    if unknown_keys:
        raise ValidationError(
            {
                "configuration": (
                    "Unsupported template options: " + ", ".join(sorted(unknown_keys))
                )
            }
        )

    title = configuration.get("title")
    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise ValidationError({"configuration": "Template title must be text."})

    columns = configuration.get("columns")
    if columns is not None:
        if not isinstance(columns, list) or not columns:
            raise ValidationError(
                {"configuration": "Template columns must be a non-empty list."}
            )
        if len(columns) > MAX_REPORT_COLUMNS or any(
            not isinstance(column, str) or not column.strip() for column in columns
        ):
            raise ValidationError(
                {"configuration": "Template columns contain invalid values."}
            )
        if len(set(columns)) != len(columns):
            raise ValidationError(
                {"configuration": "Template columns must be unique."}
            )

    default_parameters = configuration.get("default_parameters", {})
    _validate_json_object(default_parameters, "configuration")
    return configuration


def _validate_module_and_format(module, report_format):
    if module not in Report.Module.values:
        raise ValidationError({"module": "Unsupported report module."})
    if report_format not in Report.Format.values:
        raise ValidationError({"format": "Unsupported report format."})


@transaction.atomic
def create_report_template(*, name, module, report_format, configuration, actor):
    _require_active_actor(actor)
    _validate_module_and_format(module, report_format)
    if not (name or "").strip():
        raise ValidationError({"name": "A report template name is required."})
    configuration = validate_template_configuration(configuration)

    template = ReportTemplate(
        name=name.strip(),
        module=module,
        format=report_format,
        configuration=configuration,
        created_by=actor,
    )
    template.full_clean()
    template.save()
    return template


@transaction.atomic
def update_report_template(*, template_id, name, configuration):
    template = ReportTemplate.all_objects.select_for_update().get(
        pk=template_id,
        is_active=True,
    )
    if not (name or "").strip():
        raise ValidationError({"name": "A report template name is required."})
    configuration = validate_template_configuration(configuration)

    template.name = name.strip()
    template.configuration = configuration
    template.full_clean()
    template.save(update_fields=["name", "configuration", "updated_at"])
    return template


@transaction.atomic
def create_report_request(
    *,
    report_type,
    module,
    report_format,
    parameters,
    actor,
    template_id=None,
):
    _require_active_actor(actor)
    _validate_module_and_format(module, report_format)
    if not (report_type or "").strip():
        raise ValidationError({"type": "A report type is required."})
    parameters = _validate_json_object(parameters, "parameters")

    if template_id is not None:
        template = ReportTemplate.objects.get(pk=template_id)
        if template.module != module or template.format != report_format:
            raise ValidationError(
                {"template": "Template module and format must match the report."}
            )
        configuration = validate_template_configuration(template.configuration)
        merged_parameters = dict(configuration.get("default_parameters", {}))
        merged_parameters.update(parameters)
        merged_parameters["_template_id"] = str(template.pk)
        merged_parameters["_template_configuration"] = configuration
        parameters = _validate_json_object(merged_parameters, "parameters")

    report = Report(
        type=report_type.strip(),
        module=module,
        parameters=parameters,
        format=report_format,
        status=Report.Status.QUEUED,
        created_by=actor,
    )
    report.full_clean()
    report.save()
    return report


def _normalize_cell(value):
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _validate_rows(rows, configured_columns=None):
    try:
        rows = list(rows)
    except TypeError as exc:
        raise ValidationError({"rows": "Report rows must be iterable."}) from exc
    if len(rows) > MAX_REPORT_ROWS:
        raise ValidationError({"rows": "The report contains too many rows."})
    if any(not isinstance(row, dict) for row in rows):
        raise ValidationError({"rows": "Each report row must be an object."})

    if configured_columns is not None:
        columns = list(configured_columns)
    else:
        columns = []
        seen = set()
        for row in rows:
            for key in row:
                if not isinstance(key, str) or not key.strip():
                    raise ValidationError({"rows": "Report column names must be text."})
                if key not in seen:
                    seen.add(key)
                    columns.append(key)
    if len(columns) > MAX_REPORT_COLUMNS:
        raise ValidationError({"rows": "The report contains too many columns."})
    return rows, columns


def _pdf_escape(value):
    text = str(_normalize_cell(value)).replace("\\", "\\\\")
    text = text.replace("(", "\\(").replace(")", "\\)")
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _render_pdf(title, columns, rows):
    lines = [title, ""]
    if columns:
        lines.append(" | ".join(columns))
        lines.append("-" * min(110, max(10, len(lines[-1]))))
    for row in rows:
        row_text = " | ".join(str(_normalize_cell(row.get(column))) for column in columns)
        lines.extend(textwrap.wrap(row_text, width=110) or [""])
    if not rows:
        lines.append("No records matched the report parameters.")

    return _render_pdf_lines(lines)


def _render_pdf_lines(lines):

    pages = [lines[index : index + 58] for index in range(0, len(lines), 58)] or [[]]
    font_object = 3 + (2 * len(pages))
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids [{' '.join(f'{3 + 2 * i} 0 R' for i in range(len(pages)))}] "
            f"/Count {len(pages)} >>"
        ).encode("ascii"),
        font_object: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for index, page_lines in enumerate(pages):
        page_object = 3 + (2 * index)
        content_object = page_object + 1
        commands = ["BT", "/F1 10 Tf", "40 800 Td", "12 TL"]
        for line in page_lines:
            commands.append(f"({_pdf_escape(line)}) Tj T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1")
        objects[page_object] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
            f"/Resources << /Font << /F1 {font_object} 0 R >> >> "
            f"/Contents {content_object} 0 R >>"
        ).encode("ascii")
        objects[content_object] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )

    output = io.BytesIO()
    output.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_number in range(1, font_object + 1):
        offsets.append(output.tell())
        output.write(f"{object_number} 0 obj\n".encode("ascii"))
        output.write(objects[object_number])
        output.write(b"\nendobj\n")
    xref_offset = output.tell()
    output.write(f"xref\n0 {font_object + 1}\n".encode("ascii"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.write(
        (
            f"trailer\n<< /Size {font_object + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return output.getvalue()


def _render_construction_pdf(dataset):
    from arabic_reshaper import reshape
    from bidi.algorithm import get_display
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        KeepTogether,
        LongTable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    font_name = "SFLMSDejaVu"
    pdfmetrics.registerFont(
        TTFont(font_name, "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    )
    page_size = landscape(A4)
    page_width, page_height = page_size
    margin = 12 * mm
    content_width = page_width - (2 * margin)
    metadata = dataset["metadata"]
    project = dataset["project"]
    summary = dataset["summary"]

    def visual_text(value):
        text = str(value)
        if any("\u0600" <= character <= "\u06ff" for character in text):
            return get_display(reshape(text))
        return text

    def display_value(value, key=None):
        if value is None or value == "":
            return "—"
        if isinstance(value, datetime):
            moment = value
            if moment.tzinfo is not None:
                moment = moment.astimezone(timezone.utc)
                return moment.strftime("%Y-%m-%d %H:%M UTC")
            return moment.strftime("%Y-%m-%d %H:%M")
        if isinstance(value, date):
            return value.strftime("%Y-%m-%d")
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if key == "file_size" and isinstance(value, (int, float, Decimal)):
            return f"{float(value) / 1024:.1f} KB"
        if key and ("progress" in key or "percentage" in key) and isinstance(
            value, (int, float, Decimal)
        ):
            number = float(value)
            return f"{number:.0f}%" if number.is_integer() else f"{number:.1f}%"
        if isinstance(value, Decimal):
            number = float(value)
            return f"{number:.0f}" if number.is_integer() else f"{number:.2f}"
        return str(value)

    styles = getSampleStyleSheet()
    base_style = ParagraphStyle(
        "SFLMSBase",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(REPORT_TEXT),
        alignment=TA_LEFT,
        splitLongWords=True,
    )
    label_style = ParagraphStyle(
        "SFLMSLabel",
        parent=base_style,
        fontSize=6.5,
        leading=8,
        textColor=colors.HexColor(REPORT_MUTED),
    )
    heading_style = ParagraphStyle(
        "SFLMSSectionHeading",
        parent=base_style,
        fontSize=12,
        leading=15,
        textColor=colors.HexColor(REPORT_ACCENT_DARK),
        spaceBefore=8,
        spaceAfter=5,
        keepWithNext=True,
    )
    title_style = ParagraphStyle(
        "SFLMSTitle",
        parent=base_style,
        fontSize=20,
        leading=24,
        textColor=colors.HexColor(REPORT_ACCENT_DARK),
        alignment=TA_CENTER,
        spaceAfter=3,
    )
    subtitle_style = ParagraphStyle(
        "SFLMSSubtitle",
        parent=base_style,
        fontSize=9,
        leading=11,
        textColor=colors.HexColor(REPORT_MUTED),
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    table_header_style = ParagraphStyle(
        "SFLMSTableHeader",
        parent=base_style,
        fontSize=6.5,
        leading=8,
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    empty_style = ParagraphStyle(
        "SFLMSEmpty",
        parent=base_style,
        textColor=colors.HexColor(REPORT_MUTED),
        leftIndent=8,
    )

    def paragraph(value, style=base_style, key=None):
        displayed = visual_text(display_value(value, key))
        alignment = TA_RIGHT if any(
            "\u0600" <= character <= "\u06ff" for character in str(value)
        ) else style.alignment
        if alignment != style.alignment:
            style = ParagraphStyle(
                f"{style.name}RTL",
                parent=style,
                alignment=alignment,
            )
        return Paragraph(escape(displayed).replace("\n", "<br/>"), style)

    def table_style(*, header=False):
        commands = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor(REPORT_BORDER)),
            ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor(REPORT_ACCENT_LIGHTER)]),
        ]
        if header:
            commands.extend(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(REPORT_ACCENT)),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor(REPORT_ACCENT_DARK)),
                ]
            )
        return TableStyle(commands)

    story = [
        Paragraph("Construction Project Report", title_style),
        Paragraph(visual_text(project["name"]), subtitle_style),
    ]

    metadata_rows = [
        [
            paragraph("Project", label_style),
            paragraph(project["name"]),
            paragraph("Period", label_style),
            paragraph(metadata["period"]),
        ],
        [
            paragraph("Date range", label_style),
            paragraph(
                f"{display_value(metadata['date_from'])} to {display_value(metadata['date_to'])}"
                if metadata["date_from"] is not None
                else "All available history"
            ),
            paragraph("Generated", label_style),
            paragraph(metadata["generated_at"]),
        ],
        [
            paragraph("Generated by", label_style),
            paragraph(metadata["generated_by"]),
            paragraph("Project ID", label_style),
            paragraph(project["id"]),
        ],
    ]
    metadata_table = Table(
        metadata_rows,
        colWidths=[26 * mm, 70 * mm, 26 * mm, content_width - (122 * mm)],
        hAlign="LEFT",
    )
    metadata_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(REPORT_ACCENT_LIGHT)),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(REPORT_BORDER_STRONG)),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor(REPORT_BORDER)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([metadata_table, Spacer(1, 7), Paragraph("Project Overview", heading_style)])

    overview_rows = []
    for label, key in (
        ("Name", "name"),
        ("Description", "description"),
        ("Location", "location"),
        ("Facility Type", "facility_type"),
        ("Status", "status"),
        ("Start Date", "start_date"),
        ("Expected Completion", "expected_completion_date"),
        ("Actual Completion", "actual_completion_date"),
        ("Overall Progress", "overall_progress"),
    ):
        overview_rows.append(
            [paragraph(label, label_style), paragraph(project.get(key), key=key)]
        )
    overview_table = Table(overview_rows, colWidths=[38 * mm, content_width - (38 * mm)])
    overview_table.setStyle(table_style())
    story.extend([overview_table, Paragraph("Summary", heading_style)])

    summary_items = (
        ("Phases", "phase_count"),
        ("Progress Entries", "progress_count"),
        ("Daily Reports", "daily_report_count"),
        ("Materials", "material_count"),
        ("Open Material Requests", "open_material_request_count"),
        ("Failed Inspections", "failed_inspection_count"),
        ("Documents", "document_count"),
        ("Photos", "photo_count"),
    )
    summary_rows = []
    for index in range(0, len(summary_items), 2):
        left_label, left_key = summary_items[index]
        right_label, right_key = summary_items[index + 1]
        summary_rows.append(
            [
                paragraph(left_label, label_style),
                paragraph(summary[left_key]),
                paragraph(right_label, label_style),
                paragraph(summary[right_key]),
            ]
        )
    summary_table = Table(
        summary_rows,
        colWidths=[46 * mm, 20 * mm, 46 * mm, content_width - (112 * mm)],
    )
    summary_table.setStyle(table_style())
    story.append(summary_table)

    wide_keys = {
        "description",
        "work_completed",
        "notes",
        "report_content",
        "equipment_used",
        "issues",
        "reason",
        "caption",
        "original_file_name",
    }
    medium_keys = {
        "name",
        "title",
        "phase_name",
        "author_name",
        "requester_name",
        "inspector_name",
        "uploader_name",
        "progress_percentage",
        "current_progress",
        "workers_count",
        "weather_condition",
        "approval_status",
        "result",
    }
    for section in dataset["sections"]:
        columns = section["columns"]
        rows = section["rows"]
        heading = Paragraph(section["title"], heading_style)
        if not rows:
            story.append(
                KeepTogether(
                    [
                        heading,
                        Table(
                            [[paragraph(CONSTRUCTION_EMPTY_MESSAGE, empty_style)]],
                            colWidths=[content_width],
                            style=TableStyle(
                                [
                                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(REPORT_ACCENT_LIGHTER)),
                                    ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor(REPORT_BORDER)),
                                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                                ]
                            ),
                        ),
                    ]
                )
            )
            continue

        weights = [
            3
            if key in wide_keys
            else 1.6
            if key in medium_keys
            else 1.35
            if "date" in key or key.endswith("_at")
            else 1
            for key, _ in columns
        ]
        weight_total = sum(weights)
        widths = [content_width * weight / weight_total for weight in weights]
        table_rows = [
            [paragraph(label, table_header_style) for _, label in columns]
        ]
        table_rows.extend(
            [paragraph(row.get(key), key=key) for key, _ in columns] for row in rows
        )
        section_table = LongTable(
            table_rows,
            colWidths=widths,
            repeatRows=1,
            splitByRow=1,
            hAlign="LEFT",
        )
        section_table.setStyle(table_style(header=True))
        story.extend([heading, section_table])

    def page_frame(canvas, document):
        canvas.saveState()
        canvas.setFont(font_name, 7)
        canvas.setFillColor(colors.HexColor(REPORT_MUTED))
        canvas.drawString(margin, page_height - (8 * mm), "SFLMS | Construction Project Report")
        project_context = visual_text(project["name"])
        canvas.drawRightString(page_width - margin, page_height - (8 * mm), project_context)
        canvas.setStrokeColor(colors.HexColor(REPORT_BORDER_STRONG))
        canvas.setLineWidth(0.5)
        canvas.line(margin, page_height - (10 * mm), page_width - margin, page_height - (10 * mm))
        canvas.line(margin, 9 * mm, page_width - margin, 9 * mm)
        canvas.drawString(margin, 5.5 * mm, f"Generated {display_value(metadata['generated_at'])}")
        canvas.drawRightString(page_width - margin, 5.5 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=page_size,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=16 * mm,
        bottomMargin=14 * mm,
        title="Construction Project Report",
        author="SFLMS",
    )
    document.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    return output.getvalue()


def _operations_column_label(column, module=None):
    # A bare ``id`` is a facility identifier only in the operations modules,
    # whose rows are facilities. For every other module it is that module's own
    # record id, so the operations label would mislabel the column.
    if column == "id" and module is not None and module not in OPERATIONS_REPORT_MODULES:
        return "ID"
    return OPERATIONS_COLUMN_LABELS.get(
        column,
        column.replace("__", " ").replace("_", " ").title(),
    )


def _operations_report_metadata(report, title, row_count):
    parameters = _report_filters(report)
    date_from = parameters.get("date_from")
    date_to = parameters.get("date_to")
    if parameters.get("period_label"):
        period = parameters["period_label"]
    elif date_from and date_to:
        period = f"{date_from} to {date_to}"
    elif date_from:
        period = f"From {date_from}"
    elif date_to:
        period = f"Through {date_to}"
    else:
        period = "All available history"
    return {
        "title": title,
        "period": period,
        "facility": parameters.get("facility_id") or "Not specified",
        "status": parameters.get("status") or "All statuses",
        "generated_at": report.updated_at,
        "generated_by": report.created_by.full_name,
        "row_count": row_count,
    }


def _operations_display_value(value, key=None):
    if value is None or value == "":
        return "\u2014"
    if isinstance(value, datetime):
        moment = value
        if moment.tzinfo is not None:
            moment = moment.astimezone(timezone.utc)
            return moment.strftime("%Y-%m-%d %H:%M UTC")
        return moment.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if key and ("health_score" in key or "percentage" in key) and isinstance(
        value, (int, float, Decimal)
    ):
        number = float(value)
        return f"{number:.0f}%" if number.is_integer() else f"{number:.1f}%"
    if isinstance(value, Decimal):
        number = float(value)
        return f"{number:.0f}" if number.is_integer() else f"{number:.2f}"
    return str(value)


def _render_operations_pdf(report, title, columns, rows):
    from arabic_reshaper import reshape
    from bidi.algorithm import get_display
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        KeepTogether,
        LongTable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    font_name = "SFLMSDejaVu"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(
            TTFont(font_name, "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        )
    page_size = landscape(A4)
    page_width, page_height = page_size
    margin = 12 * mm
    content_width = page_width - (2 * margin)
    metadata = _operations_report_metadata(report, title, len(rows))

    accent = colors.HexColor(REPORT_ACCENT)
    accent_dark = colors.HexColor(REPORT_ACCENT_DARK)
    accent_light = colors.HexColor(REPORT_ACCENT_LIGHT)
    accent_lighter = colors.HexColor(REPORT_ACCENT_LIGHTER)
    border = colors.HexColor(REPORT_BORDER)
    text_color = colors.HexColor(REPORT_TEXT)
    muted = colors.HexColor(REPORT_MUTED)

    def visual_text(value):
        text = str(value)
        if any("\u0600" <= character <= "\u06ff" for character in text):
            return get_display(reshape(text))
        return text

    styles = getSampleStyleSheet()
    base_style = ParagraphStyle(
        "OperationsBase",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=7,
        leading=9,
        textColor=text_color,
        alignment=TA_LEFT,
        splitLongWords=True,
    )
    label_style = ParagraphStyle(
        "OperationsLabel",
        parent=base_style,
        fontSize=6.5,
        leading=8,
        textColor=accent_dark,
    )
    title_style = ParagraphStyle(
        "OperationsTitle",
        parent=base_style,
        fontSize=20,
        leading=24,
        textColor=accent_dark,
        alignment=TA_CENTER,
        spaceAfter=3,
    )
    subtitle_style = ParagraphStyle(
        "OperationsSubtitle",
        parent=base_style,
        fontSize=9,
        leading=11,
        textColor=muted,
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    heading_style = ParagraphStyle(
        "OperationsSectionHeading",
        parent=base_style,
        fontSize=12,
        leading=15,
        textColor=accent_dark,
        spaceBefore=8,
        spaceAfter=5,
    )
    header_style = ParagraphStyle(
        "OperationsTableHeader",
        parent=base_style,
        fontSize=6.5,
        leading=8,
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    empty_style = ParagraphStyle(
        "OperationsEmpty",
        parent=base_style,
        fontSize=8,
        leading=11,
        textColor=muted,
        leftIndent=8,
    )

    def paragraph(value, style=base_style, key=None):
        displayed = visual_text(_operations_display_value(value, key))
        alignment = TA_RIGHT if any(
            "\u0600" <= character <= "\u06ff" for character in str(value)
        ) else style.alignment
        if alignment != style.alignment:
            style = ParagraphStyle(f"{style.name}RTL", parent=style, alignment=alignment)
        return Paragraph(escape(displayed).replace("\n", "<br/>"), style)

    story = [
        Paragraph(visual_text(title), title_style),
        Paragraph("SFLMS Operations Report", subtitle_style),
    ]
    metadata_rows = [
        [
            paragraph("Report Type", label_style),
            paragraph(title),
            paragraph("Period", label_style),
            paragraph(metadata["period"]),
        ],
        [
            paragraph("Facility Filter", label_style),
            paragraph(metadata["facility"]),
            paragraph("Status Filter", label_style),
            paragraph(metadata["status"]),
        ],
        [
            paragraph("Generated By", label_style),
            paragraph(metadata["generated_by"]),
            paragraph("Generated At", label_style),
            paragraph(metadata["generated_at"]),
        ],
    ]
    metadata_table = Table(
        metadata_rows,
        colWidths=[29 * mm, 67 * mm, 29 * mm, content_width - (125 * mm)],
        hAlign="LEFT",
    )
    metadata_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), accent_light),
                ("BOX", (0, 0), (-1, -1), 0.7, border),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, border),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([metadata_table, Spacer(1, 7), Paragraph("Summary", heading_style)])
    summary_table = Table(
        [[paragraph("Records", label_style), paragraph(metadata["row_count"]) ]],
        colWidths=[38 * mm, content_width - (38 * mm)],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), accent_lighter),
                ("BOX", (0, 0), (-1, -1), 0.5, border),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(summary_table)

    if rows and columns:
        wide_keys = {"description", "reason", "root_cause", "resolution", "location"}
        medium_keys = {"name", "asset_type", "category", "serial_number", "fault_type"}
        weights = [
            2.7
            if key in wide_keys
            else 1.7
            if key in medium_keys
            else 1.4
            if "date" in key or key.endswith("_at")
            else 1
            for key in columns
        ]
        weight_total = sum(weights)
        widths = [content_width * weight / weight_total for weight in weights]
        table_rows = [
            [paragraph(_operations_column_label(column, report.module), header_style) for column in columns]
        ]
        table_rows.extend(
            [paragraph(row.get(column), key=column) for column in columns] for row in rows
        )
        data_table = LongTable(
            table_rows,
            colWidths=widths,
            repeatRows=1,
            splitByRow=1,
            hAlign="LEFT",
        )
        data_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("GRID", (0, 0), (-1, -1), 0.35, border),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, accent_lighter]),
                    ("BACKGROUND", (0, 0), (-1, 0), accent),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, accent_dark),
                ]
            )
        )
        story.extend([Paragraph("Report Data", heading_style), data_table])
    else:
        empty_table = Table(
            [[paragraph(OPERATIONS_EMPTY_MESSAGE, empty_style)]],
            colWidths=[content_width],
        )
        empty_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), accent_lighter),
                    ("BOX", (0, 0), (-1, -1), 0.4, border),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ]
            )
        )
        story.append(
            KeepTogether([Paragraph("Report Data", heading_style), empty_table])
        )

    def page_frame(canvas, document):
        canvas.saveState()
        canvas.setFont(font_name, 7)
        canvas.setFillColor(muted)
        canvas.drawString(margin, page_height - (8 * mm), "SFLMS | Operations Report")
        canvas.drawRightString(
            page_width - margin,
            page_height - (8 * mm),
            visual_text(title),
        )
        canvas.setStrokeColor(border)
        canvas.setLineWidth(0.5)
        canvas.line(margin, page_height - (10 * mm), page_width - margin, page_height - (10 * mm))
        canvas.line(margin, 9 * mm, page_width - margin, 9 * mm)
        canvas.drawString(
            margin,
            5.5 * mm,
            f"Generated {_operations_display_value(metadata['generated_at'])}",
        )
        canvas.drawRightString(page_width - margin, 5.5 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=page_size,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=16 * mm,
        bottomMargin=14 * mm,
        title=title,
        author="SFLMS",
    )
    document.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    return output.getvalue()


def _xlsx_cell(reference, value):
    value = _normalize_cell(value)
    if isinstance(value, bool):
        return f'<c r="{reference}" t="b"><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{reference}" t="n"><v>{value}</v></c>'
    return (
        f'<c r="{reference}" t="inlineStr"><is><t xml:space="preserve">'
        f"{escape(str(value))}</t></is></c>"
    )


def _column_name(index):
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _render_xlsx(columns, rows):
    sheet_rows = []
    all_rows = [dict(zip(columns, columns))] + rows if columns else rows
    for row_number, row in enumerate(all_rows, start=1):
        cells = [
            _xlsx_cell(f"{_column_name(column_number)}{row_number}", row.get(column))
            for column_number, column in enumerate(columns, start=1)
        ]
        sheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '</Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>',
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '</Relationships>',
        )
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return output.getvalue()


def _construction_xlsx_cell(reference, value, *, key=None, style=None):
    if style is not None:
        style_id = style
    elif isinstance(value, datetime):
        style_id = 6
    elif isinstance(value, date):
        style_id = 5
    elif key and (
        "progress" in key or "percentage" in key or "health_score" in key
    ) and isinstance(
        value, (int, float, Decimal)
    ):
        style_id = 7
    elif isinstance(value, int) and not isinstance(value, bool):
        style_id = 8
    elif isinstance(value, (float, Decimal)):
        style_id = 9
    else:
        style_id = 4

    if value is None or value == "":
        value = "—"
    if isinstance(value, datetime):
        moment = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
        serial = (moment - datetime(1899, 12, 30)).total_seconds() / 86400
        return f'<c r="{reference}" s="{style_id}" t="n"><v>{serial}</v></c>'
    if isinstance(value, date):
        serial = (value - date(1899, 12, 30)).days
        return f'<c r="{reference}" s="{style_id}" t="n"><v>{serial}</v></c>'
    if style is None and style_id == 7:
        return f'<c r="{reference}" s="{style_id}" t="n"><v>{float(value) / 100}</v></c>'
    if isinstance(value, bool):
        value = "Yes" if value else "No"
    if isinstance(value, (int, float, Decimal)) and style_id in {8, 9}:
        return f'<c r="{reference}" s="{style_id}" t="n"><v>{value}</v></c>'
    normalized = _normalize_cell(value)
    return (
        f'<c r="{reference}" s="{style_id}" t="inlineStr">'
        f'<is><t xml:space="preserve">{escape(str(normalized))}</t></is></c>'
    )


def _construction_xlsx_width(key, label, rows):
    longest = len(label)
    for row in rows:
        value = row.get(key)
        if isinstance(value, datetime):
            candidate = 19
        elif isinstance(value, date):
            candidate = 10
        else:
            candidate = max((len(line) for line in str(_normalize_cell(value)).splitlines()), default=0)
        longest = max(longest, candidate)
    wide_keys = {
        "description",
        "work_completed",
        "notes",
        "report_content",
        "equipment_used",
        "issues",
        "reason",
        "caption",
    }
    maximum = 42 if key in wide_keys or key == "value" else 32
    return min(max(longest + 2, 12), maximum)


def _worksheet_xml(
    columns,
    rows,
    *,
    sheet_title,
    context,
    empty_message=None,
    summary=False,
    adaptive_row_heights=False,
):
    last_column = _column_name(max(1, len(columns)))
    last_row = 5 if not rows else 4 + len(rows)
    rendered_rows = [
        '<row r="1" ht="24" customHeight="1">'
        + _construction_xlsx_cell("A1", sheet_title, style=1)
        + "</row>",
        '<row r="2" ht="20" customHeight="1">'
        + _construction_xlsx_cell("A2", context, style=2)
        + "</row>",
    ]
    header_cells = [
        _construction_xlsx_cell(
            f"{_column_name(column_number)}4",
            label,
            style=3,
        )
        for column_number, (_, label) in enumerate(columns, start=1)
    ]
    rendered_rows.append(
        f'<row r="4" ht="26" customHeight="1">{"".join(header_cells)}</row>'
    )
    column_widths = [
        _construction_xlsx_width(key, label, rows) for key, label in columns
    ]
    if rows:
        for row_number, row in enumerate(rows, start=5):
            cells = []
            for column_number, (key, _) in enumerate(columns, start=1):
                cell_style = 11 if summary and column_number == 1 else None
                cells.append(
                    _construction_xlsx_cell(
                        f"{_column_name(column_number)}{row_number}",
                        row.get(key),
                        key=key,
                        style=cell_style,
                    )
                )
            row_height = 22
            if adaptive_row_heights:
                line_count = 1
                for (key, _), width in zip(columns, column_widths):
                    value = _operations_display_value(row.get(key), key)
                    usable_width = max(8, int(width) - 2)
                    wrapped_lines = sum(
                        max(1, math.ceil(len(line) / usable_width))
                        for line in str(value).splitlines() or [""]
                    )
                    line_count = max(line_count, wrapped_lines)
                row_height = min(72, max(22, 14 * line_count + 6))
            rendered_rows.append(
                f'<row r="{row_number}" ht="{row_height}" customHeight="1">'
                f'{"".join(cells)}</row>'
            )
    elif empty_message:
        rendered_rows.append(
            '<row r="5" ht="24" customHeight="1">'
            + _construction_xlsx_cell("A5", empty_message, style=10)
            + "</row>"
        )

    column_xml = "".join(
        f'<col min="{index}" max="{index}" width="{width:.1f}" customWidth="1"/>'
        for index, width in enumerate(column_widths, start=1)
    )
    merged_cells = [f'<mergeCell ref="A1:{last_column}1"/>', f'<mergeCell ref="A2:{last_column}2"/>']
    if not rows and empty_message:
        merged_cells.append(f'<mergeCell ref="A5:{last_column}5"/>')
    filter_reference = f"A4:{last_column}{last_row}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{last_column}{last_row}"/>'
        '<sheetViews><sheetView showGridLines="0" workbookViewId="0">'
        '<pane ySplit="4" topLeftCell="A5" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft" activeCell="A5" sqref="A5"/>'
        '</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="18"/>'
        f'<cols>{column_xml}</cols>'
        f'<sheetData>{"".join(rendered_rows)}</sheetData>'
        f'<autoFilter ref="{filter_reference}"/>'
        f'<mergeCells count="{len(merged_cells)}">{"".join(merged_cells)}</mergeCells>'
        '<pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>'
        '<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0" paperSize="9"/>'
        '</worksheet>'
    )


def _construction_xlsx_styles():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<numFmts count="5">'
        '<numFmt numFmtId="164" formatCode="yyyy-mm-dd"/>'
        '<numFmt numFmtId="165" formatCode="yyyy-mm-dd hh:mm"/>'
        '<numFmt numFmtId="166" formatCode="0%"/>'
        '<numFmt numFmtId="167" formatCode="#,##0"/>'
        '<numFmt numFmtId="168" formatCode="#,##0.00"/>'
        '</numFmts>'
        '<fonts count="4">'
        '<font><sz val="10"/><name val="Calibri"/><family val="2"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/><sz val="16"/><name val="Calibri"/></font>'
        f'<font><color rgb="{_argb(REPORT_ACCENT_ON_DARK)}"/><sz val="10"/><name val="Calibri"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Calibri"/></font>'
        '</fonts>'
        '<fills count="5">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        f'<fill><patternFill patternType="solid"><fgColor rgb="{_argb(REPORT_ACCENT_DARK)}"/><bgColor indexed="64"/></patternFill></fill>'
        f'<fill><patternFill patternType="solid"><fgColor rgb="{_argb(REPORT_ACCENT)}"/><bgColor indexed="64"/></patternFill></fill>'
        f'<fill><patternFill patternType="solid"><fgColor rgb="{_argb(REPORT_ACCENT_LIGHT)}"/><bgColor indexed="64"/></patternFill></fill>'
        '</fills>'
        '<borders count="2">'
        '<border><left/><right/><top/><bottom/><diagonal/></border>'
        f'<border><left style="thin"><color rgb="{_argb(REPORT_BORDER)}"/></left>'
        f'<right style="thin"><color rgb="{_argb(REPORT_BORDER)}"/></right>'
        f'<top style="thin"><color rgb="{_argb(REPORT_BORDER)}"/></top>'
        f'<bottom style="thin"><color rgb="{_argb(REPORT_BORDER)}"/></bottom><diagonal/></border>'
        '</borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="12">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="3" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>'
        '<xf numFmtId="165" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>'
        '<xf numFmtId="166" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="top"/></xf>'
        '<xf numFmtId="167" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="top"/></xf>'
        '<xf numFmtId="168" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="top"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="top" wrapText="1"/></xf>'
        '</cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )


def _render_construction_xlsx(dataset):
    summary_rows = []
    for label, value in (
        ("Report", dataset["title"]),
        ("Project", dataset["project"]["name"]),
        ("Description", dataset["project"]["description"]),
        ("Location", dataset["project"]["location"]),
        ("Facility Type", dataset["project"]["facility_type"]),
        ("Project Status", dataset["project"]["status"]),
        ("Start Date", dataset["project"]["start_date"]),
        (
            "Expected Completion",
            dataset["project"]["expected_completion_date"],
        ),
        ("Actual Completion", dataset["project"]["actual_completion_date"]),
        ("Overall Progress", dataset["project"]["overall_progress"]),
        ("Period", dataset["metadata"]["period"]),
        ("Date From", dataset["metadata"]["date_from"]),
        ("Date To", dataset["metadata"]["date_to"]),
        ("Generated At", dataset["metadata"]["generated_at"]),
        ("Generated By", dataset["metadata"]["generated_by"]),
        ("Phases", dataset["summary"]["phase_count"]),
        ("Progress Entries", dataset["summary"]["progress_count"]),
        ("Daily Reports", dataset["summary"]["daily_report_count"]),
        ("Materials", dataset["summary"]["material_count"]),
        (
            "Open Material Requests",
            dataset["summary"]["open_material_request_count"],
        ),
        ("Failed Inspections", dataset["summary"]["failed_inspection_count"]),
        ("Documents", dataset["summary"]["document_count"]),
        ("Photos", dataset["summary"]["photo_count"]),
    ):
        summary_rows.append({"field": label, "value": value})

    sheets = [
        (
            "Summary",
            (("field", "Field"), ("value", "Value")),
            summary_rows,
            None,
        )
    ]
    sheets.extend(
        (
            section["sheet_name"],
            section["columns"],
            section["rows"],
            CONSTRUCTION_EMPTY_MESSAGE,
        )
        for section in dataset["sections"]
    )
    context = (
        f"Project: {dataset['project']['name']} | "
        f"Period: {dataset['metadata']['period']}"
    )

    content_types = [
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    workbook_sheets = []
    workbook_relationships = []
    for index, (name, _, _, _) in enumerate(sheets, start=1):
        content_types.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        workbook_sheets.append(
            f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        )
        workbook_relationships.append(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
    workbook_relationships.append(
        '<Relationship Id="rId10" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            f'{"".join(content_types)}</Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>',
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<bookViews><workbookView activeTab="0"/></bookViews>'
            f'<sheets>{"".join(workbook_sheets)}</sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{"".join(workbook_relationships)}</Relationships>',
        )
        archive.writestr("xl/styles.xml", _construction_xlsx_styles())
        for index, (name, columns, rows, empty_message) in enumerate(sheets, start=1):
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _worksheet_xml(
                    columns,
                    rows,
                    sheet_title=f"Construction Project Report - {name}",
                    context=context,
                    empty_message=empty_message,
                    summary=name == "Summary",
                ),
            )
    return output.getvalue()


def _operations_xlsx_styles():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<numFmts count="5">'
        '<numFmt numFmtId="164" formatCode="yyyy-mm-dd"/>'
        '<numFmt numFmtId="165" formatCode="yyyy-mm-dd hh:mm"/>'
        '<numFmt numFmtId="166" formatCode="0%"/>'
        '<numFmt numFmtId="167" formatCode="#,##0"/>'
        '<numFmt numFmtId="168" formatCode="#,##0.00"/>'
        '</numFmts>'
        '<fonts count="4">'
        '<font><sz val="10"/><name val="Calibri"/><family val="2"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/><sz val="16"/><name val="Calibri"/></font>'
        f'<font><color rgb="{_argb(REPORT_ACCENT_LIGHT)}"/><sz val="10"/><name val="Calibri"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Calibri"/></font>'
        '</fonts>'
        '<fills count="5">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        f'<fill><patternFill patternType="solid"><fgColor rgb="{_argb(REPORT_ACCENT_DARK)}"/><bgColor indexed="64"/></patternFill></fill>'
        f'<fill><patternFill patternType="solid"><fgColor rgb="{_argb(REPORT_ACCENT)}"/><bgColor indexed="64"/></patternFill></fill>'
        f'<fill><patternFill patternType="solid"><fgColor rgb="{_argb(REPORT_ACCENT_LIGHT)}"/><bgColor indexed="64"/></patternFill></fill>'
        '</fills>'
        '<borders count="2">'
        '<border><left/><right/><top/><bottom/><diagonal/></border>'
        f'<border><left style="thin"><color rgb="{_argb(REPORT_BORDER)}"/></left>'
        f'<right style="thin"><color rgb="{_argb(REPORT_BORDER)}"/></right>'
        f'<top style="thin"><color rgb="{_argb(REPORT_BORDER)}"/></top>'
        f'<bottom style="thin"><color rgb="{_argb(REPORT_BORDER)}"/></bottom><diagonal/></border>'
        '</borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="12">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="3" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>'
        '<xf numFmtId="165" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>'
        '<xf numFmtId="166" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="top"/></xf>'
        '<xf numFmtId="167" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="top"/></xf>'
        '<xf numFmtId="168" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="top"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="top" wrapText="1"/></xf>'
        '</cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )


def _render_operations_xlsx(report, title, columns, rows):
    metadata = _operations_report_metadata(report, title, len(rows))
    labelled_columns = tuple(
        (column, _operations_column_label(column, report.module)) for column in columns
    )
    context_parts = [
        f"Period: {metadata['period']}",
        f"Records: {metadata['row_count']}",
        f"Facility filter: {metadata['facility']}",
        f"Status filter: {metadata['status']}",
        f"Generated by: {metadata['generated_by']}",
    ]
    worksheet = _worksheet_xml(
        labelled_columns,
        rows,
        sheet_title=f"SFLMS - {title}",
        context=" | ".join(context_parts),
        empty_message=OPERATIONS_EMPTY_MESSAGE,
        adaptive_row_heights=True,
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '</Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>',
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<bookViews><workbookView activeTab="0"/></bookViews>'
            '<sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets>'
            '</workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>',
        )
        archive.writestr("xl/styles.xml", _operations_xlsx_styles())
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return output.getvalue()


def _template_configuration_for(report):
    configuration_snapshot = report.parameters.get("_template_configuration")
    if configuration_snapshot is not None:
        return validate_template_configuration(configuration_snapshot)
    template_id = report.parameters.get("_template_id")
    if not template_id:
        return {}
    try:
        template = ReportTemplate.objects.get(pk=template_id)
    except (ReportTemplate.DoesNotExist, ValueError) as exc:
        raise ValidationError({"template": "The selected report template is unavailable."}) from exc
    if template.module != report.module or template.format != report.format:
        raise ValidationError({"template": "The report template no longer matches."})
    return validate_template_configuration(template.configuration)


def _report_filters(report):
    parameters = {
        key: value
        for key, value in report.parameters.items()
        if not key.startswith("_")
    }
    allowed = {"project_id", "facility_id", "status", "date_from", "date_to", "period_label"}
    unknown = set(parameters) - allowed
    if unknown:
        raise ValidationError(
            {"parameters": "Unsupported report filters: " + ", ".join(sorted(unknown))}
        )
    return parameters


def _construction_report_dates(parameters):
    date_from_value = parameters.get("date_from")
    date_to_value = parameters.get("date_to")
    if bool(date_from_value) != bool(date_to_value):
        raise ValidationError(
            {"parameters": "Construction reports require both date_from and date_to."}
        )
    if not date_from_value:
        return None, None
    try:
        date_from = date.fromisoformat(str(date_from_value))
        date_to = date.fromisoformat(str(date_to_value))
    except ValueError as exc:
        raise ValidationError(
            {"parameters": "Construction report dates must use YYYY-MM-DD."}
        ) from exc
    if date_from > date_to:
        raise ValidationError(
            {"parameters": "date_from cannot be later than date_to."}
        )
    return date_from, date_to


def _construction_report_project(report, parameters):
    from apps.projects.models import Project, ProjectAssignment
    from apps.users.models import Role, User

    project_id = parameters.get("project_id")
    if not project_id:
        raise ValidationError(
            {"parameters": "Construction reports require an assigned project."}
        )
    try:
        project = Project.objects.get(pk=project_id)
    except (Project.DoesNotExist, ValueError) as exc:
        raise ValidationError(
            {"parameters": "The selected construction project is unavailable."}
        ) from exc

    actor = report.created_by
    if (
        not actor
        or actor.status != User.STATUS_ACTIVE
        or not actor.role_id
    ):
        raise ValidationError(
            {"actor": "The report creator is no longer active."}
        )
    if actor.role.name == Role.SUPER_ADMIN:
        return project
    if actor.role.name != Role.CONSTRUCTION_MANAGER or not ProjectAssignment.objects.filter(
        project=project,
        user=actor,
        is_active=True,
    ).exists():
        raise ValidationError(
            {"actor": "The report creator is no longer assigned to this project."}
        )
    return project


def _apply_construction_date_range(queryset, field, date_from, date_to):
    if date_from is None:
        return queryset
    lookup_prefix = f"{field}__date" if field != "report_date" else field
    return queryset.filter(
        **{
            f"{lookup_prefix}__gte": date_from,
            f"{lookup_prefix}__lte": date_to,
        }
    )


def build_construction_report_dataset(report, *, title=None, daily_columns=None):
    """Build the frozen Construction Project Report v1 dataset."""
    from apps.construction.models import DailyReport, QualityInspection, SitePhoto
    from apps.materials.models import Material, MaterialRequest
    from apps.projects.models import PhaseProgressLog, ProjectDocument, ProjectPhase
    from apps.projects.services import calculate_project_progress

    if report.module != Report.Module.CONSTRUCTION:
        raise ValidationError({"module": "A construction report is required."})
    parameters = _report_filters(report)
    allowed_parameters = {"project_id", "date_from", "date_to", "period_label"}
    unknown_parameters = set(parameters) - allowed_parameters
    if unknown_parameters:
        raise ValidationError(
            {
                "parameters": (
                    "Unsupported construction report filters: "
                    + ", ".join(sorted(unknown_parameters))
                )
            }
        )
    date_from, date_to = _construction_report_dates(parameters)
    project = _construction_report_project(report, parameters)

    phases = list(
        ProjectPhase.objects.filter(project=project)
        .select_related("approved_by")
        .order_by("sequence_number", "id")
    )
    progress_logs = _apply_construction_date_range(
        PhaseProgressLog.objects.filter(phase__project=project).select_related(
            "phase", "created_by"
        ),
        "created_at",
        date_from,
        date_to,
    ).order_by("created_at", "id")
    daily_reports = _apply_construction_date_range(
        DailyReport.objects.filter(project=project).select_related(
            "phase", "created_by"
        ),
        "report_date",
        date_from,
        date_to,
    ).order_by("report_date", "created_at", "id")
    materials = Material.objects.filter(project=project).order_by("name", "id")
    material_requests = (
        MaterialRequest.objects.filter(project=project)
        .select_related("material", "created_by")
        .order_by("created_at", "id")
    )
    inspections = _apply_construction_date_range(
        QualityInspection.objects.filter(project=project).select_related(
            "phase", "inspector"
        ),
        "inspected_at",
        date_from,
        date_to,
    ).order_by("inspected_at", "id")
    documents = _apply_construction_date_range(
        ProjectDocument.objects.filter(project=project).select_related("created_by"),
        "created_at",
        date_from,
        date_to,
    ).order_by("created_at", "id")
    photos = _apply_construction_date_range(
        SitePhoto.objects.filter(project=project).select_related("phase"),
        "captured_at",
        date_from,
        date_to,
    ).order_by("captured_at", "id")

    section_rows = {
        "phases": [
            {
                "sequence_number": phase.sequence_number,
                "name": phase.name,
                "priority": phase.get_priority_display(),
                "status": phase.get_status_display(),
                "start_date": phase.start_date,
                "expected_completion_date": phase.expected_completion_date,
                "actual_start_date": phase.actual_start_date,
                "actual_completion_date": phase.actual_completion_date,
                "current_progress": phase.current_progress,
                "approval_status": "Approved" if phase.approved_by_id else "Not Approved",
            }
            for phase in phases
        ],
        "progress": [
            {
                "phase_name": log.phase.name,
                "progress_percentage": log.progress_percentage,
                "work_completed": log.work_completed,
                "notes": log.notes,
                "author_name": log.created_by.full_name,
                "recorded_at": log.created_at,
            }
            for log in progress_logs
        ],
        "daily_reports": [
            {
                "project_id": str(item.project_id),
                "phase_id": str(item.phase_id) if item.phase_id else "",
                "report_date": item.report_date,
                "phase_name": item.phase.name if item.phase_id else "",
                "title": item.title,
                "report_content": item.report_content,
                "progress_percentage": item.progress_percentage,
                "workers_count": item.workers_count,
                "weather_condition": item.weather_condition,
                "equipment_used": item.equipment_used,
                "issues": item.issues,
                "author_name": item.created_by.full_name,
            }
            for item in daily_reports
        ],
        "materials": [
            {
                "name": material.name,
                "unit": material.get_unit_display(),
                "quantity_required": material.quantity_required,
                "quantity_used": material.quantity_used,
                "quantity_remaining": material.quantity_remaining,
                "min_stock_threshold": material.min_stock_threshold,
                "low_stock": material.quantity_remaining
                <= material.min_stock_threshold,
            }
            for material in materials
        ],
        "material_requests": [
            {
                "material_name": item.material.name,
                "quantity_requested": item.quantity_requested,
                "unit": item.material.get_unit_display(),
                "reason": item.reason,
                "priority": item.get_priority_display(),
                "status": item.get_status_display(),
                "requester_name": item.created_by.full_name,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in material_requests
        ],
        "quality": [
            {
                "phase_name": item.phase.name,
                "title": item.title,
                "inspector_name": item.inspector.full_name,
                "score": item.score,
                "result": item.get_result_display(),
                "notes": item.notes,
                "inspected_at": item.inspected_at,
            }
            for item in inspections
        ],
        "documents": [
            {
                "title": item.title,
                "document_type": item.document_type,
                "original_file_name": item.original_file_name,
                "mime_type": item.mime_type,
                "file_size": item.file_size,
                "uploader_name": item.created_by.full_name,
                "uploaded_at": item.created_at,
            }
            for item in documents
        ],
        "photos": [
            {
                "caption": item.caption,
                "phase_name": item.phase.name if item.phase_id else "",
                "original_file_name": item.original_file_name,
                "mime_type": item.mime_type,
                "file_size": item.file_size,
                "captured_at": item.captured_at,
            }
            for item in photos
        ],
    }

    definitions = []
    for key, sheet_name, default_columns in CONSTRUCTION_REPORT_SECTIONS:
        columns = default_columns
        if key == "daily_reports" and daily_columns is not None:
            columns = tuple(
                (column, CONSTRUCTION_DAILY_COLUMN_LABELS[column])
                for column in daily_columns
            )
        rows, _ = _validate_rows(
            section_rows[key],
            [column for column, _ in columns],
        )
        definitions.append(
            {
                "key": key,
                "title": sheet_name,
                "sheet_name": sheet_name,
                "columns": columns,
                "rows": rows,
            }
        )

    open_request_statuses = {
        MaterialRequest.Status.SUBMITTED,
        MaterialRequest.Status.REVIEWED,
        MaterialRequest.Status.APPROVED,
    }
    period = parameters.get("period_label") or (
        f"{date_from.isoformat()} to {date_to.isoformat()}"
        if date_from is not None
        else "All available history"
    )
    return {
        "title": title or "Construction Project Report",
        "metadata": {
            "period": period,
            "date_from": date_from,
            "date_to": date_to,
            "generated_at": report.updated_at,
            "generated_by": report.created_by.full_name,
        },
        "project": {
            "id": str(project.pk),
            "name": project.name,
            "description": project.description,
            "location": project.location,
            "facility_type": project.get_facility_type_display(),
            "status": project.get_status_display(),
            "start_date": project.start_date,
            "expected_completion_date": project.expected_completion_date,
            "actual_completion_date": project.actual_completion_date,
            "overall_progress": calculate_project_progress(project),
        },
        "summary": {
            "phase_count": len(section_rows["phases"]),
            "progress_count": len(section_rows["progress"]),
            "daily_report_count": len(section_rows["daily_reports"]),
            "material_count": len(section_rows["materials"]),
            "material_request_count": len(section_rows["material_requests"]),
            "open_material_request_count": sum(
                item.status in open_request_statuses for item in material_requests
            ),
            "quality_count": len(section_rows["quality"]),
            "failed_inspection_count": sum(
                item.result == QualityInspection.Result.FAILED for item in inspections
            ),
            "document_count": len(section_rows["documents"]),
            "photo_count": len(section_rows["photos"]),
        },
        "sections": definitions,
    }


def build_domain_report_rows(report):
    """Read report rows from the owning domain instead of client-supplied data."""
    parameters = _report_filters(report)
    columns = DOMAIN_REPORT_COLUMNS[report.module]

    if report.module == Report.Module.PROJECTS:
        from apps.projects.models import Project

        queryset = Project.objects.all()
        if parameters.get("project_id"):
            queryset = queryset.filter(pk=parameters["project_id"])
        if parameters.get("status"):
            queryset = queryset.filter(status=parameters["status"])
        if parameters.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=parameters["date_from"])
        if parameters.get("date_to"):
            queryset = queryset.filter(created_at__date__lte=parameters["date_to"])
    elif report.module == Report.Module.CONSTRUCTION:
        from apps.construction.models import DailyReport

        queryset = DailyReport.objects.all()
        if parameters.get("project_id"):
            queryset = queryset.filter(project_id=parameters["project_id"])
        if parameters.get("date_from"):
            queryset = queryset.filter(report_date__gte=parameters["date_from"])
        if parameters.get("date_to"):
            queryset = queryset.filter(report_date__lte=parameters["date_to"])
    elif report.module == Report.Module.MATERIALS:
        from apps.materials.models import Material

        queryset = Material.objects.all()
        if parameters.get("project_id"):
            queryset = queryset.filter(project_id=parameters["project_id"])
        if parameters.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=parameters["date_from"])
        if parameters.get("date_to"):
            queryset = queryset.filter(created_at__date__lte=parameters["date_to"])
    elif report.module == Report.Module.ASSETS:
        from apps.assets.models import Asset

        queryset = Asset.objects.all()
        if parameters.get("facility_id"):
            queryset = queryset.filter(facility_id=parameters["facility_id"])
        if parameters.get("status"):
            queryset = queryset.filter(current_status=parameters["status"])
        if parameters.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=parameters["date_from"])
        if parameters.get("date_to"):
            queryset = queryset.filter(created_at__date__lte=parameters["date_to"])
    elif report.module == Report.Module.MAINTENANCE:
        from apps.maintenance.models import MaintenanceOrder

        queryset = MaintenanceOrder.objects.all()
        if parameters.get("facility_id"):
            queryset = queryset.filter(asset__facility_id=parameters["facility_id"])
        if parameters.get("status"):
            queryset = queryset.filter(status=parameters["status"])
        if parameters.get("date_from"):
            queryset = queryset.filter(
                expected_execution_date__gte=parameters["date_from"]
            )
        if parameters.get("date_to"):
            queryset = queryset.filter(
                expected_execution_date__lte=parameters["date_to"]
            )
    elif report.module == Report.Module.FAULTS:
        from apps.maintenance.models import Fault

        queryset = Fault.objects.all()
        if parameters.get("facility_id"):
            queryset = queryset.filter(asset__facility_id=parameters["facility_id"])
        if parameters.get("status"):
            queryset = queryset.filter(status=parameters["status"])
        if parameters.get("date_from"):
            queryset = queryset.filter(discovery_time__date__gte=parameters["date_from"])
        if parameters.get("date_to"):
            queryset = queryset.filter(discovery_time__date__lte=parameters["date_to"])
    elif report.module == Report.Module.OPERATIONAL_PERFORMANCE:
        from django.db.models import Avg, Count, Q
        from apps.facilities.models import Facility

        queryset = Facility.objects.annotate(
            total_assets=Count("assets", filter=Q(assets__is_active=True), distinct=True),
            operational_assets=Count("assets", filter=Q(assets__is_active=True, assets__current_status="operational"), distinct=True),
            maintenance_assets=Count("assets", filter=Q(assets__is_active=True, assets__current_status="under_maintenance"), distinct=True),
            out_of_service_assets=Count("assets", filter=Q(assets__is_active=True, assets__current_status="out_of_service"), distinct=True),
            average_health_score=Avg("assets__health_score", filter=Q(assets__is_active=True)),
        )
        if parameters.get("facility_id"):
            queryset = queryset.filter(pk=parameters["facility_id"])
        if parameters.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=parameters["date_from"])
        if parameters.get("date_to"):
            queryset = queryset.filter(created_at__date__lte=parameters["date_to"])
    elif report.module == Report.Module.SECURITY:
        from apps.security.models import Incident

        queryset = Incident.objects.all()
        if parameters.get("facility_id"):
            queryset = queryset.filter(facility_id=parameters["facility_id"])
        if parameters.get("status"):
            queryset = queryset.filter(status=parameters["status"])
        if parameters.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=parameters["date_from"])
        if parameters.get("date_to"):
            queryset = queryset.filter(created_at__date__lte=parameters["date_to"])
    elif report.module == Report.Module.USERS:
        from apps.users.models import User

        queryset = User.objects.select_related("role").all()
        if parameters.get("status"):
            queryset = queryset.filter(status=parameters["status"])
        if parameters.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=parameters["date_from"])
        if parameters.get("date_to"):
            queryset = queryset.filter(created_at__date__lte=parameters["date_to"])
    elif report.module == Report.Module.ALERTS:
        from apps.security.models import SecurityAlert

        queryset = SecurityAlert.objects.all()
        if parameters.get("facility_id"):
            queryset = queryset.filter(facility_id=parameters["facility_id"])
        if parameters.get("status"):
            queryset = queryset.filter(status=parameters["status"])
        if parameters.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=parameters["date_from"])
        if parameters.get("date_to"):
            queryset = queryset.filter(created_at__date__lte=parameters["date_to"])
    else:
        from apps.security.models import IncidentAction

        queryset = IncidentAction.objects.all()
        if parameters.get("facility_id"):
            queryset = queryset.filter(incident__facility_id=parameters["facility_id"])
        if parameters.get("date_from"):
            queryset = queryset.filter(taken_at__date__gte=parameters["date_from"])
        if parameters.get("date_to"):
            queryset = queryset.filter(taken_at__date__lte=parameters["date_to"])

    return list(queryset.order_by("created_at").values(*columns))


@transaction.atomic
def begin_report_generation(*, report_id):
    report = Report.all_objects.select_for_update().get(
        pk=report_id,
        is_active=True,
    )
    if report.status != Report.Status.QUEUED:
        raise ValidationError({"status": "Only a queued report can start generation."})
    report.status = Report.Status.PROCESSING
    report.full_clean()
    report.save(update_fields=["status", "updated_at"])
    return report


@transaction.atomic
def complete_report_generation(*, report_id, content, extension):
    report = Report.all_objects.select_for_update().get(
        pk=report_id,
        is_active=True,
    )
    if report.status != Report.Status.PROCESSING:
        raise ValidationError(
            {"status": "Only a generating report can be completed."}
        )
    expected_extension = ".pdf" if report.format == Report.Format.PDF else ".xlsx"
    if extension != expected_extension:
        raise ValidationError({"file_path": "Generated file format does not match."})

    generated_file = ContentFile(content, name=f"report{extension}")
    saved_name = None
    try:
        validate_report_file(generated_file)
        report.file_path.save(generated_file.name, generated_file, save=False)
        saved_name = report.file_path.name
        report.status = Report.Status.COMPLETED
        # The generated content was validated before storage. Excluding the
        # committed FieldFile avoids reopening and retaining an OS file handle
        # during model validation (notably on Windows workers).
        report.full_clean(exclude={"file_path"})
        report.save(update_fields=["file_path", "status", "updated_at"])
    except Exception:
        if saved_name:
            report.file_path.storage.delete(saved_name)
        raise
    finally:
        generated_file.close()
    return report


@transaction.atomic
def fail_report_generation(*, report_id, error):
    report = Report.all_objects.select_for_update().get(
        pk=report_id,
        is_active=True,
    )
    if report.status not in {Report.Status.QUEUED, Report.Status.PROCESSING}:
        raise ValidationError(
            {"status": "Only a pending or generating report can fail."}
        )
    parameters = dict(report.parameters)
    parameters["_generation_error"] = str(error)[:2000]
    report.parameters = _validate_json_object(parameters, "parameters")
    report.status = Report.Status.FAILED
    report.full_clean()
    report.save(update_fields=["parameters", "status", "updated_at"])
    return report


@transaction.atomic
def requeue_failed_report(*, report_id):
    report = Report.all_objects.select_for_update().get(pk=report_id, is_active=True)
    if report.status != Report.Status.FAILED:
        raise ValidationError({"status": "Only a failed report can be requeued."})
    parameters = dict(report.parameters)
    parameters.pop("_generation_error", None)
    report.parameters = _validate_json_object(parameters, "parameters")
    report.status = Report.Status.QUEUED
    report.full_clean()
    report.save(update_fields=["parameters", "status", "updated_at"])
    return report


def generate_report(*, report_id):
    report = begin_report_generation(report_id=report_id)
    try:
        _validate_json_object(report.parameters, "parameters")
        configuration = _template_configuration_for(report)
        configured_columns = configuration.get("columns")
        if configured_columns is not None:
            invalid_columns = set(configured_columns) - set(
                DOMAIN_REPORT_COLUMNS[report.module]
            )
            if invalid_columns:
                raise ValidationError(
                    {
                        "configuration": (
                            "Template columns are not available for this module: "
                            + ", ".join(sorted(invalid_columns))
                        )
                    }
                )
        title = configuration.get("title") or report.type
        if report.module == Report.Module.CONSTRUCTION:
            dataset = build_construction_report_dataset(
                report,
                title=title,
                daily_columns=configured_columns,
            )
            if report.format == Report.Format.PDF:
                content = _render_construction_pdf(dataset)
                extension = ".pdf"
            else:
                content = _render_construction_xlsx(dataset)
                extension = ".xlsx"
        else:
            domain_rows = build_domain_report_rows(report)
            rows, columns = _validate_rows(domain_rows, configured_columns)
            # Every non-construction module renders through the same styled
            # generator so projects, materials, security, users, alerts and
            # response reports belong to the same report family as the
            # Construction Manager report instead of falling back to an
            # unstyled, latin-1 text dump.
            if report.format == Report.Format.PDF:
                content = _render_operations_pdf(
                    report,
                    title,
                    columns,
                    rows,
                )
                extension = ".pdf"
            else:
                content = _render_operations_xlsx(
                    report,
                    title,
                    columns,
                    rows,
                )
                extension = ".xlsx"
        return complete_report_generation(
            report_id=report.pk,
            content=content,
            extension=extension,
        )
    except Exception as exc:
        fail_report_generation(report_id=report.pk, error=exc)
        raise
