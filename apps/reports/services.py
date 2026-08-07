import io
import json
import math
import textwrap
import zipfile
from datetime import date, datetime
from decimal import Decimal
from html import escape
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction

from .models import Report, ReportTemplate


MAX_PARAMETER_BYTES = 64 * 1024
MAX_REPORT_ROWS = 10_000
MAX_REPORT_COLUMNS = 100
TEMPLATE_CONFIGURATION_KEYS = {"title", "columns", "default_parameters"}
DOMAIN_REPORT_COLUMNS = {
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
    Report.Module.SECURITY: (
        "incident_number", "facility_id", "incident_type", "description",
        "location", "severity_level", "status", "closed_at",
    ),
}


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
    allowed = {"project_id", "facility_id", "status", "date_from", "date_to"}
    unknown = set(parameters) - allowed
    if unknown:
        raise ValidationError(
            {"parameters": "Unsupported report filters: " + ", ".join(sorted(unknown))}
        )
    return parameters


def build_domain_report_rows(report):
    """Read report rows from the owning domain instead of client-supplied data."""
    parameters = _report_filters(report)
    columns = DOMAIN_REPORT_COLUMNS[report.module]

    if report.module == Report.Module.CONSTRUCTION:
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
    elif report.module == Report.Module.ASSETS:
        from apps.assets.models import Asset

        queryset = Asset.objects.all()
        if parameters.get("facility_id"):
            queryset = queryset.filter(facility_id=parameters["facility_id"])
        if parameters.get("status"):
            queryset = queryset.filter(current_status=parameters["status"])
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
    else:
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
        report.file_path.save(generated_file.name, generated_file, save=False)
        saved_name = report.file_path.name
        report.status = Report.Status.COMPLETED
        report.full_clean()
        report.save(update_fields=["file_path", "status", "updated_at"])
    except Exception:
        if saved_name:
            report.file_path.storage.delete(saved_name)
        raise
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
        domain_rows = build_domain_report_rows(report)
        rows, columns = _validate_rows(domain_rows, configured_columns)
        title = configuration.get("title") or report.type
        if report.format == Report.Format.PDF:
            content = _render_pdf(title, columns, rows)
            extension = ".pdf"
        else:
            content = _render_xlsx(columns, rows)
            extension = ".xlsx"
        return complete_report_generation(
            report_id=report.pk,
            content=content,
            extension=extension,
        )
    except Exception as exc:
        fail_report_generation(report_id=report.pk, error=exc)
        raise
