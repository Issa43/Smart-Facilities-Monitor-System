"""Three demo projects that walk a facility through its whole life cycle.

    Tartus    a new logistics centre under construction, managed from Damascus
    Homs      a healthcare complex under rehabilitation
    Damascus  a business tower in operation: assets, faults, a smoke incident

Every name, person and company is fictional. A project that already exists
(matched by name) is skipped, so re-running the command never duplicates data.

The system has no risk register, so each project's risks live in one of its
documents (and the active ones in its daily reports). Construction incidents
are recorded as quality inspections, daily-report issues and a material
request; operational incidents as asset faults and a security incident.
Records are created through the ORM, not the services, so nothing is
notified.
"""

import io
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.assets.models import Asset
from apps.construction.models import DailyReport, QualityInspection
from apps.facilities.models import Facility, FacilityAssignment
from apps.maintenance.models import Fault
from apps.materials.models import Material, MaterialRequest
from apps.projects.models import (
    Project,
    ProjectAssignment,
    ProjectDocument,
    ProjectPhase,
)
from apps.security.models import Incident, IncidentAction, SecurityAlert
from apps.users.models import Role, User

DAMASCUS = ZoneInfo("Asia/Damascus")
DEMO_NOTE = "وثيقة تجريبية أُعدّت لأغراض العرض، وجميع الأسماء والبيانات فيها افتراضية."
UNSPECIFIED = "غير محدد"

TARTUS = "إنشاء مركز الشام اللوجستي"
HOMS = "إعادة تأهيل مجمع النور الصحي"
DAMASCUS_TOWER = "برج الياسمين للأعمال"

# (email, username, full name, assignment role on the Tartus project). All are
# Construction Managers, because only that role can be assigned to a project;
# their profession is recorded in the project description, not as a role.
TARTUS_TEAM = [
    ("yazan.ali@sflms.local", "demo_yazan_ali", "م. يزن العلي", "engineer"),
    ("sara.hamdan@sflms.local", "demo_sara_hamdan", "م. سارة حمدان", "engineer"),
    ("louay.mansour@sflms.local", "demo_louay_mansour", "م. لؤي منصور", "engineer"),
    ("ahmad.khalil@sflms.local", "demo_ahmad_khalil", "أحمد خليل", "supervisor"),
    ("rana.mahmoud@sflms.local", "demo_rana_mahmoud", "رنا محمود", "viewer"),
]


def at(year, month, day, hour=9, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=DAMASCUS)


def saved(instance):
    instance.full_clean()
    instance.save()
    return instance


def backdate(instance, moment):
    """Give a seeded record the creation time of the event it describes."""
    type(instance).all_objects.filter(pk=instance.pk).update(created_at=moment)


# ---------------------------------------------------------------------------
# Demo PDF documents
# ---------------------------------------------------------------------------

class _ArabicPdf:
    """A plain A4 page flow for right-to-left text, tables and headings."""

    FONT = "DemoArabic"
    FONT_BOLD = "DemoArabicBold"

    def __init__(self):
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas

        if self.FONT not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(
                TTFont(self.FONT, "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
            )
            pdfmetrics.registerFont(
                TTFont(self.FONT_BOLD, "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
            )
        self._metrics = pdfmetrics
        self.buffer = io.BytesIO()
        self.canvas = canvas.Canvas(self.buffer, pagesize=A4)
        self.width, self.height = A4
        self.margin = 56
        self.y = self.height - self.margin

    @staticmethod
    def shape(text):
        from arabic_reshaper import reshape
        from bidi.algorithm import get_display

        return get_display(reshape(text))

    def _text_width(self, text, font, size):
        return self._metrics.stringWidth(self.shape(text), font, size)

    def _wrap(self, text, font, size, width):
        lines, current = [], ""
        for word in text.split():
            candidate = f"{current} {word}".strip()
            if current and self._text_width(candidate, font, size) > width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines or [""]

    def _need(self, height):
        if self.y - height < self.margin + 20:
            self._footer()
            self.canvas.showPage()
            self.y = self.height - self.margin

    def _footer(self):
        self.canvas.setFont(self.FONT, 8)
        self.canvas.setFillGray(0.4)
        self.canvas.drawCentredString(self.width / 2, self.margin / 2, self.shape(DEMO_NOTE))
        self.canvas.setFillGray(0)

    def title(self, text, subtitle):
        self._need(60)
        self.canvas.setFont(self.FONT_BOLD, 17)
        self.canvas.drawRightString(self.width - self.margin, self.y, self.shape(text))
        self.y -= 24
        self.canvas.setFont(self.FONT, 11)
        self.canvas.drawRightString(self.width - self.margin, self.y, self.shape(subtitle))
        self.y -= 10
        self.canvas.line(self.margin, self.y, self.width - self.margin, self.y)
        self.y -= 22

    def heading(self, text):
        self._need(30)
        self.canvas.setFont(self.FONT_BOLD, 12.5)
        self.canvas.drawRightString(self.width - self.margin, self.y, self.shape(text))
        self.y -= 20

    def paragraph(self, text, size=10.5):
        leading = size * 1.6
        for line in self._wrap(text, self.FONT, size, self.width - 2 * self.margin):
            self._need(leading)
            self.canvas.setFont(self.FONT, size)
            self.canvas.drawRightString(self.width - self.margin, self.y, self.shape(line))
            self.y -= leading
        self.y -= 6

    def table(self, headers, rows, fractions):
        size, leading, pad = 9, 13, 5
        total = self.width - 2 * self.margin
        widths = [total * f for f in fractions]
        for index, row in enumerate([headers] + rows):
            font = self.FONT_BOLD if index == 0 else self.FONT
            cells = [
                self._wrap(str(value), font, size, width - 2 * pad)
                for value, width in zip(row, widths)
            ]
            height = max(len(lines) for lines in cells) * leading + 2 * pad
            self._need(height)
            right = self.width - self.margin
            top = self.y
            if index == 0:
                self.canvas.setFillGray(0.9)
                self.canvas.rect(self.margin, top - height, total, height, stroke=0, fill=1)
                self.canvas.setFillGray(0)
            for lines, width in zip(cells, widths):
                self.canvas.rect(right - width, top - height, width, height)
                self.canvas.setFont(font, size)
                line_y = top - pad - size
                for line in lines:
                    self.canvas.drawRightString(right - pad, line_y, self.shape(line))
                    line_y -= leading
                right -= width
            self.y = top - height
        self.y -= 14

    def build(self):
        self._footer()
        self.canvas.save()
        return self.buffer.getvalue()


def demo_pdf(title, project_name, blocks):
    pdf = _ArabicPdf()
    pdf.title(title, project_name)
    for kind, *content in blocks:
        getattr(pdf, kind)(*content)
    return pdf.build()


def add_document(project, file_name, document_type, title, blocks, author, created):
    document = ProjectDocument(
        project=project,
        document_type=document_type,
        title=title,
        file=ContentFile(demo_pdf(title, project.name, blocks), name=file_name),
        created_by=author,
    )
    document.save()  # ProjectDocument.save() derives the file metadata and validates
    backdate(document, created)
    return document


# ---------------------------------------------------------------------------
# Shared builders
# ---------------------------------------------------------------------------

def add_phases(project, phases, author):
    """phases: (name, start, end, progress, status, actual_start, actual_end, priority)."""
    created = []
    for sequence, (name, start, end, progress, status, actual_start, actual_end, priority) in enumerate(
        phases, start=1
    ):
        created.append(
            saved(
                ProjectPhase(
                    project=project,
                    name=name,
                    sequence_number=sequence,
                    start_date=start,
                    expected_completion_date=end,
                    actual_start_date=actual_start,
                    actual_completion_date=actual_end,
                    current_progress=Decimal(progress),
                    status=status,
                    priority=priority,
                    created_by=author,
                )
            )
        )
    return created


def add_assets(facility, assets, author):
    """assets: (code, name, asset_type, category, location, installed, operating, status, health, notes)."""
    created = {}
    for code, name, asset_type, category, location, installed, operating, status, health, notes in assets:
        created[code] = saved(
            Asset(
                facility=facility,
                name=f"{name} ({code.split('-', 1)[1]})",
                asset_type=asset_type,
                category=category,
                serial_number=code,
                manufacturer=UNSPECIFIED,
                model=UNSPECIFIED,
                location_inside_facility=location,
                installation_date=installed,
                operation_date=operating,
                current_status=status,
                health_score=Decimal(health),
                notes=notes,
                created_by=author,
            )
        )
    return created


def phase_table(phases):
    labels = {"completed": "مكتملة", "in_progress": "قيد التنفيذ", "not_started": "لم تبدأ"}
    return [(p.name, labels[p.status], f"{p.current_progress:.0f}%") for p in phases]


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Add the three fictional demo projects (Tartus, Homs, Damascus) to the database."

    def handle(self, *args, **options):
        self.people = self._people()
        for name, builder in (
            (TARTUS, self._tartus),
            (HOMS, self._homs),
            (DAMASCUS_TOWER, self._damascus),
        ):
            if Project.all_objects.filter(name=name).exists():
                self.stdout.write(f"skipped (already exists): {name}")
                continue
            with transaction.atomic():
                builder()
            self.stdout.write(self.style.SUCCESS(f"added: {name}"))

    # -- people --------------------------------------------------------------

    def _existing(self, role_name, preferred_email):
        active = User.objects.filter(role__name=role_name, status=User.STATUS_ACTIVE)
        user = active.filter(email=preferred_email).first() or active.order_by("created_at").first()
        if user is None:
            raise CommandError(f"The demo projects need an active {role_name} user.")
        return user

    def _people(self):
        people = {
            "admin": self._existing(Role.SUPER_ADMIN, "admin@sflms.local"),
            "construction": self._existing(Role.CONSTRUCTION_MANAGER, "construction@sflms.local"),
            "operations": self._existing(Role.OPERATIONS_MANAGER, "operations@sflms.local"),
            "officer": self._existing(Role.SECURITY_OFFICER, "officer@sflms.local"),
        }
        # Every security officer who already watches a facility also watches
        # the operational tower, so the demo incident shows for whoever logs in.
        people["officers"] = list(
            User.objects.filter(
                role__name=Role.SECURITY_OFFICER,
                status=User.STATUS_ACTIVE,
                facility_assignments__is_active=True,
            ).distinct()
        ) or [people["officer"]]

        construction_role = Role.objects.get(name=Role.CONSTRUCTION_MANAGER)
        for email, username, full_name, _ in TARTUS_TEAM:
            user = User.objects.filter(email=email).first()
            if user is None:
                # No password: these are team members shown on the project,
                # not accounts anyone is meant to log in with.
                user = User.objects.create_user(
                    email=email,
                    username=username,
                    full_name=full_name,
                    password=None,
                    role=construction_role,
                )
            people[username] = user
        return people

    def _assign_construction(self, project, extra=()):
        admin = self.people["admin"]
        saved(
            ProjectAssignment(
                project=project,
                user=self.people["construction"],
                role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
                created_by=admin,
            )
        )
        for user, role_type in extra:
            saved(ProjectAssignment(project=project, user=user, role_type=role_type, created_by=admin))

    def _assign_facility(self, facility, with_security):
        admin = self.people["admin"]
        saved(
            FacilityAssignment(
                facility=facility,
                user=self.people["operations"],
                role_type=FacilityAssignment.RoleType.OPERATIONS_MANAGER,
                created_by=admin,
            )
        )
        if with_security:
            for officer in self.people["officers"]:
                saved(
                    FacilityAssignment(
                        facility=facility,
                        user=officer,
                        role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
                        created_by=admin,
                    )
                )

    # -- 1. Tartus: new construction ------------------------------------------

    def _tartus(self):
        p = self.people
        admin = p["admin"]
        yazan, sara, louay = p["demo_yazan_ali"], p["demo_sara_hamdan"], p["demo_louay_mansour"]
        ahmad, rana = p["demo_ahmad_khalil"], p["demo_rana_mahmoud"]

        project = saved(
            Project(
                name=TARTUS,
                facility_type=Project.FacilityType.COMMERCIAL,
                location="طرطوس - سوريا",
                latitude=Decimal("34.889000"),
                longitude=Decimal("35.887000"),
                start_date=date(2026, 3, 1),
                expected_completion_date=date(2027, 3, 1),
                status=Project.Status.IN_PROGRESS,
                description=(
                    "إنشاء مركز لوجستي جديد في محافظة طرطوس تابع لشركة استثمارية تُدار من دمشق، "
                    "ويضم مستودعات ومكاتب إدارية ومناطق تحميل وخدمات تشغيلية. يتيح المشروع توضيح "
                    "دور النظام في الحفاظ على رؤية مركزية لتطور المنشأة ومراحلها ومخاطرها ووثائقها "
                    "وأصولها رغم البعد الجغرافي بين الإدارة وموقع التنفيذ.\n\n"
                    "الاسم بالإنكليزية: Al-Sham Logistics Center\n"
                    "القطاع: لوجستي / تجاري — نوع المشروع: إنشاء منشأة جديدة — الأولوية: مرتفعة\n"
                    "الجهة المالكة: شركة الشام للاستثمارات (اسم تجريبي)\n\n"
                    "الفريق: م. يزن العلي (هندسة مدنية، متابعة الأعمال الإنشائية)، "
                    "م. سارة حمدان (هندسة معمارية، متابعة الأعمال المعمارية والتشطيبات)، "
                    "م. لؤي منصور (هندسة كهربائية، متابعة الشبكات الكهربائية)، "
                    "أحمد خليل (إدارة مشاريع، متابعة تقدم المشروع والتنسيق)، "
                    "رنا محمود (إدارة استثمارية، متابعة المشروع من الإدارة المركزية)."
                ),
                created_by=admin,
            )
        )
        self._assign_construction(
            project,
            [(user, role) for user, (*_, role) in zip((yazan, sara, louay, ahmad, rana), TARTUS_TEAM)],
        )

        phases = add_phases(
            project,
            [
                ("الدراسات والمخططات الأولية", date(2026, 3, 1), date(2026, 3, 31), "100", "completed", date(2026, 3, 1), date(2026, 3, 28), "high"),
                ("التراخيص وتجهيز الموقع", date(2026, 4, 1), date(2026, 4, 30), "100", "completed", date(2026, 4, 1), date(2026, 4, 27), "high"),
                ("الحفريات والأساسات", date(2026, 5, 1), date(2026, 6, 30), "100", "completed", date(2026, 5, 2), date(2026, 6, 29), "critical"),
                ("الهيكل الإنشائي", date(2026, 7, 1), date(2026, 10, 31), "82", "in_progress", date(2026, 7, 1), None, "critical"),
                ("الأعمال المعمارية", date(2026, 8, 15), date(2026, 12, 15), "45", "in_progress", date(2026, 8, 17), None, "high"),
                ("الأعمال الكهربائية والميكانيكية", date(2026, 9, 1), date(2027, 1, 15), "35", "in_progress", date(2026, 9, 1), None, "high"),
                ("التشطيبات", date(2026, 9, 20), date(2027, 1, 31), "5", "in_progress", date(2026, 9, 22), None, "medium"),
                ("تركيب الأصول والتجهيزات", date(2027, 1, 15), date(2027, 2, 15), "0", "not_started", None, None, "medium"),
                ("الاختبارات والتشغيل التجريبي", date(2027, 2, 10), date(2027, 3, 1), "0", "not_started", None, None, "high"),
            ],
            admin,
        )
        structure, architecture, services = phases[3], phases[4], phases[5]

        # Incident 1: a services clash, found and fixed.
        saved(
            DailyReport(
                project=project,
                phase=services,
                report_date=date(2026, 9, 17),
                title="تعارض مسار كهربائي مع قناة تهوية",
                progress_percentage=Decimal("33"),
                weather_condition="مشمس",
                workers_count=34,
                equipment_used=["سقالات", "رافعة شوكية"],
                report_content="تنفيذ تمديدات الخدمات في الطابق الإداري.",
                issues=(
                    "تم اكتشاف تعارض بين مسار كهربائي وقناة تهوية أثناء تنفيذ الخدمات في الطابق "
                    "الإداري. الإجراء: مراجعة المخطط وتعديل المسار قبل استكمال الإغلاق."
                ),
                created_by=louay,
            )
        )
        saved(
            QualityInspection(
                project=project,
                phase=services,
                title="مراجعة تنسيق الخدمات في الطابق الإداري",
                inspector=louay,
                score=Decimal("80"),
                result=QualityInspection.Result.PASSED_WITH_NOTES,
                notes=(
                    "رُصد تعارض بين مسار كهربائي وقناة تهوية، وعُدّل المسار وفق المخطط المراجَع "
                    "قبل استكمال الإغلاق. الحالة: تمت المعالجة."
                ),
                inspected_at=at(2026, 9, 18, 11),
                created_by=louay,
            )
        )

        # Incident 2: warehouse doors arriving late, still being followed up.
        doors = saved(
            Material(
                project=project,
                name="أبواب المستودعات",
                unit=Material.Unit.EACH,
                quantity_required=Decimal("12"),
                quantity_used=Decimal("0"),
                quantity_remaining=Decimal("12"),
                min_stock_threshold=Decimal("0"),
                created_by=ahmad,
            )
        )
        request = saved(
            MaterialRequest(
                project=project,
                material=doors,
                quantity_requested=Decimal("12"),
                reason=(
                    "توريد أبواب المستودعات. التوريد متأخر عن الموعد المخطط، مع احتمال تأخير جزء "
                    "من أعمال الإغلاق والتشطيب. الحالة: قيد المتابعة مع المورد."
                ),
                priority=MaterialRequest.Priority.HIGH,
                status=MaterialRequest.Status.APPROVED,
                created_by=ahmad,
            )
        )
        backdate(request, at(2026, 8, 20))
        saved(
            DailyReport(
                project=project,
                phase=architecture,
                report_date=date(2026, 9, 24),
                title="تأخر توريد أبواب المستودعات",
                progress_percentage=Decimal("44"),
                weather_condition="غائم جزئياً",
                workers_count=41,
                equipment_used=["سقالات"],
                report_content="متابعة الأعمال المعمارية في المستودعات والمكاتب الإدارية.",
                issues=(
                    "تأخر توريد أبواب المستودعات عن الموعد المخطط، مع احتمال تأخير جزء من أعمال "
                    "الإغلاق والتشطيب. الحالة: قيد المتابعة."
                ),
                created_by=ahmad,
            )
        )
        saved(
            DailyReport(
                project=project,
                phase=structure,
                report_date=date(2026, 9, 29),
                title="متابعة أعمال الهيكل الإنشائي",
                progress_percentage=Decimal("82"),
                weather_condition="مشمس",
                workers_count=46,
                equipment_used=["رافعة برجية", "خلاطة بيتون", "سقالات"],
                report_content="استكمال عناصر الهيكل الإنشائي في المستويات العليا.",
                issues=(
                    "مخاطر نشطة: العمل على الارتفاعات في أجزاء الهيكل والواجهات، وتنظيم أماكن "
                    "تخزين مواد البناء لتجنب إعاقة الحركة في الموقع."
                ),
                created_by=yazan,
            )
        )

        risks = [
            ("العمل على الارتفاعات", "سلامة", "مرتفعة", "نشط", "استمرار تنفيذ أجزاء من الهيكل والواجهات في مستويات مرتفعة"),
            ("تأخر مواد التشطيب", "زمني / تشغيلي", "متوسطة", "تحت المتابعة", "احتمال تأثير تأخر التوريد في الجدول"),
            ("تعارض مسارات الخدمات", "فني", "متوسطة", "قيد المعالجة", "تعارض بين بعض التمديدات الكهربائية والميكانيكية"),
            ("تخزين مواد البناء", "سلامة / موقع", "متوسطة", "نشط", "ضرورة تنظيم أماكن التخزين لتجنب إعاقة الحركة"),
        ]
        docs = [
            ("Architectural_Plans.pdf", "drawing", "المخططات المعمارية", date(2026, 3, 25), sara, [
                ("paragraph", "مجموعة المخططات المعمارية لمركز الشام اللوجستي في طرطوس."),
                ("table", ["عنصر المنشأة", "محتوى المخططات"], [
                    ["المستودعات", "المساقط الأفقية والمقاطع والواجهات"],
                    ["المكاتب الإدارية", "توزيع الفراغات والمداخل والممرات"],
                    ["مناطق التحميل", "مسارات الحركة وأماكن التحميل والتفريغ"],
                    ["الخدمات التشغيلية", "غرف الخدمات والمرافق المساندة"],
                ], [0.35, 0.65]),
            ]),
            ("Structural_Plans.pdf", "drawing", "المخططات الإنشائية", date(2026, 3, 26), yazan, [
                ("paragraph", "المخططات الإنشائية للأساسات والهيكل الإنشائي."),
                ("table", ["الجزء", "الحالة في الموقع"], [
                    ["الحفريات والأساسات", "مكتملة"],
                    ["الهيكل الإنشائي", "قيد التنفيذ"],
                ], [0.5, 0.5]),
            ]),
            ("Electrical_Plans.pdf", "drawing", "المخططات الكهربائية", date(2026, 3, 27), louay, [
                ("paragraph", "مخططات الشبكات الكهربائية ولوحات التوزيع والإنارة في المستودعات والمكاتب الإدارية ومناطق التحميل."),
            ]),
            ("MEP_Coordination.pdf", "drawing", "مخطط تنسيق الخدمات الكهربائية والميكانيكية", date(2026, 9, 18), louay, [
                ("paragraph", "مخطط تنسيق مسارات الخدمات الكهربائية والميكانيكية."),
                ("heading", "تعديل بتاريخ 17/09/2026"),
                ("paragraph", "عُدّل مسار كهربائي تعارض مع قناة تهوية في الطابق الإداري، قبل استكمال الإغلاق."),
            ]),
            ("Weekly_Progress_Report.pdf", "report", "تقرير التقدم الأسبوعي", date(2026, 9, 29), ahmad, [
                ("heading", "حالة المراحل"),
                ("table", ["المرحلة", "الحالة", "الإنجاز"], phase_table(phases), [0.55, 0.25, 0.2]),
                ("heading", "أحداث الأسبوع"),
                ("paragraph", "تأخر توريد أبواب المستودعات، مع احتمال تأخير جزء من أعمال الإغلاق والتشطيب. الحالة: قيد المتابعة."),
                ("paragraph", "تمت معالجة تعارض المسار الكهربائي مع قناة التهوية في الطابق الإداري."),
            ]),
            ("Site_Risk_Assessment.pdf", "report", "تقييم مخاطر الموقع", date(2026, 9, 15), ahmad, [
                ("paragraph", "سجل مخاطر موقع مركز الشام اللوجستي."),
                ("table", ["الخطر", "التصنيف", "الخطورة", "الحالة", "الوصف"], risks, [0.2, 0.15, 0.12, 0.15, 0.38]),
            ]),
        ]
        for file_name, document_type, title, created, author, blocks in docs:
            add_document(project, file_name, document_type, title, blocks, author, at(created.year, created.month, created.day))

    # -- 2. Homs: rehabilitation ----------------------------------------------

    def _homs(self):
        p = self.people
        admin, samer, operations = p["admin"], p["construction"], p["operations"]

        facility = saved(
            Facility(
                name="مجمع النور الصحي",
                type=Facility.Type.HEALTHCARE,
                location="حمص - سوريا",
                status=Facility.Status.UNDER_MAINTENANCE,
                created_by=admin,
            )
        )
        self._assign_facility(facility, with_security=False)

        project = saved(
            Project(
                name=HOMS,
                facility=facility,
                facility_type=Project.FacilityType.HEALTHCARE,
                location="حمص - سوريا",
                latitude=Decimal("34.732400"),
                longitude=Decimal("36.713700"),
                start_date=date(2026, 4, 15),
                expected_completion_date=date(2027, 9, 30),
                status=Project.Status.IN_PROGRESS,
                description=(
                    "إعادة تأهيل منشأة صحية تتطلب معالجة الأجزاء الإنشائية والخدمات الكهربائية "
                    "والميكانيكية وأنظمة السلامة قبل إعادة وضع المنشأة في الخدمة. يستخدم هذا المثال "
                    "لإظهار أهمية استمرارية المعلومات وإدارة المخاطر والأحداث خلال مشاريع إعادة "
                    "التأهيل طويلة الأمد.\n\n"
                    "الاسم بالإنكليزية: Al-Noor Medical Complex Rehabilitation\n"
                    "القطاع: صحي — نوع المشروع: إعادة تأهيل / إعادة إعمار — الأولوية: حرجة"
                ),
                created_by=admin,
            )
        )
        self._assign_construction(project)

        phases = add_phases(
            project,
            [
                ("تقييم الحالة الحالية والأضرار", date(2026, 4, 15), date(2026, 5, 15), "100", "completed", date(2026, 4, 15), date(2026, 5, 14), "critical"),
                ("توثيق المنشأة ووضع خطة التأهيل", date(2026, 5, 16), date(2026, 6, 15), "100", "completed", date(2026, 5, 16), date(2026, 6, 12), "high"),
                ("إزالة العناصر غير الآمنة", date(2026, 6, 16), date(2026, 7, 31), "100", "completed", date(2026, 6, 16), date(2026, 7, 29), "critical"),
                ("التدعيم والإصلاح الإنشائي", date(2026, 8, 1), date(2027, 1, 31), "68", "in_progress", date(2026, 8, 1), None, "critical"),
                ("تأهيل الشبكة الكهربائية", date(2026, 8, 15), date(2027, 2, 28), "42", "in_progress", date(2026, 8, 16), None, "high"),
                ("المياه والصرف والخدمات", date(2026, 9, 1), date(2027, 3, 31), "35", "in_progress", date(2026, 9, 1), None, "medium"),
                ("أنظمة الإطفاء والسلامة", date(2026, 9, 10), date(2027, 4, 30), "20", "in_progress", date(2026, 9, 12), None, "critical"),
                ("التجهيزات الطبية", date(2027, 5, 1), date(2027, 8, 15), "0", "not_started", None, None, "high"),
                ("الاختبارات النهائية", date(2027, 8, 16), date(2027, 9, 30), "0", "not_started", None, None, "high"),
            ],
            admin,
        )
        structural, electrical = phases[3], phases[4]

        assets = add_assets(
            facility,
            [
                ("NOOR-G-01", "المولد الاحتياطي", "generator", "كهربائية", "غرفة المولدات", date(2012, 6, 1), date(2012, 7, 1), "under_maintenance", "70", "تحت الاختبار."),
                ("NOOR-MDB-01", "لوحة التوزيع", "panel", "كهربائية", "غرفة الكهرباء الرئيسية", date(2012, 6, 1), date(2012, 7, 1), "under_maintenance", "55", "قيد إعادة التأهيل."),
                ("NOOR-E-01", "مصعد المرضى", "elevator", "نقل عمودي", "الجناح الرئيسي", date(2012, 6, 1), date(2012, 7, 1), "out_of_service", "35", "خارج الخدمة أثناء التأهيل."),
                ("NOOR-FP-01", "مضخة الحريق", "pump", "سلامة", "غرفة المضخات", date(2012, 6, 1), date(2012, 7, 1), "under_maintenance", "65", "بانتظار الاختبار."),
                ("NOOR-WT-01", "خزان المياه", "tank", "خدمات", "السطح", date(2012, 6, 1), date(2012, 7, 1), "operational", "90", "عامل."),
                ("NOOR-FA-01", "نظام إنذار الحريق", "fire_alarm", "سلامة", "كامل المبنى", date(2012, 6, 1), date(2012, 7, 1), "under_maintenance", "50", "قيد إعادة التأهيل."),
            ],
            admin,
        )

        # Incident: a switchboard fault during testing, resolved.
        panel_fault = saved(
            Fault(
                asset=assets["NOOR-MDB-01"],
                fault_type="عطل كهربائي",
                description="خلل أثناء اختبار لوحة التوزيع MDB-01 ضمن مرحلة تأهيل الشبكة الكهربائية.",
                severity=Fault.Severity.MAJOR,
                discovery_time=at(2026, 9, 21, 11),
                reported_by=operations,
                status=Fault.Status.RESOLVED,
                root_cause="خلل في إحدى دارات اللوحة ظهر أثناء اختبار التشغيل.",
                resolution="فصل الدارة وفحص اللوحة قبل إعادة الاختبار.",
                resolved_at=at(2026, 9, 22, 13),
                created_by=operations,
            )
        )
        backdate(panel_fault, at(2026, 9, 21, 11))
        saved(
            DailyReport(
                project=project,
                phase=electrical,
                report_date=date(2026, 9, 21),
                title="خلل أثناء اختبار لوحة كهربائية",
                progress_percentage=Decimal("40"),
                weather_condition="مشمس",
                workers_count=22,
                equipment_used=["أجهزة قياس كهربائية"],
                report_content="اختبار لوحة التوزيع الرئيسية MDB-01 بعد تأهيلها.",
                issues="ظهر خلل أثناء اختبار لوحة التوزيع MDB-01. الإجراء: فصل الدارة وفحص اللوحة قبل إعادة الاختبار.",
                created_by=samer,
            )
        )

        # Incident: an additional crack found under the finishes, still open.
        saved(
            QualityInspection(
                project=project,
                phase=structural,
                title="معاينة تشقق إضافي في عنصر إنشائي — الطابق الثاني، الجناح الشرقي",
                inspector=samer,
                score=Decimal("45"),
                result=QualityInspection.Result.FAILED,
                notes=(
                    "لوحظ تشقق أثناء إزالة طبقات الإكساء لم يكن ظاهراً في المعاينة الأولية. الإجراء: "
                    "إيقاف العمل في المنطقة المتأثرة مؤقتاً وتحويل الحالة إلى الفريق الهندسي لإجراء "
                    "التقييم. الحالة: قيد المعالجة."
                ),
                inspected_at=at(2026, 9, 26, 10, 30),
                created_by=samer,
            )
        )
        saved(
            DailyReport(
                project=project,
                phase=structural,
                report_date=date(2026, 9, 26),
                title="اكتشاف تشقق إضافي في عنصر إنشائي",
                progress_percentage=Decimal("68"),
                weather_condition="غائم جزئياً",
                workers_count=28,
                equipment_used=["سقالات", "معدات تدعيم"],
                report_content="إزالة طبقات الإكساء في الطابق الثاني، الجناح الشرقي، تمهيداً لأعمال التدعيم.",
                issues=(
                    "لوحظ تشقق إضافي في عنصر إنشائي لم يكن ظاهراً في المعاينة الأولية. أُوقف العمل في "
                    "المنطقة المتأثرة مؤقتاً وحُوّلت الحالة إلى الفريق الهندسي لإجراء التقييم."
                ),
                created_by=samer,
            )
        )

        risks = [
            ("وجود أضرار إنشائية غير ظاهرة", "إنشائي", "مرتفع", "تحت المراقبة"),
            ("تمديدات كهربائية قديمة", "كهربائي", "مرتفع", "قيد المعالجة"),
            ("العمل في أجزاء غير مستقرة", "سلامة بشرية", "مرتفع", "نشط"),
            ("تأخر توريد تجهيزات", "تشغيلي", "متوسط", "مراقب"),
            ("فقدان معلومات بين مراحل التأهيل", "إداري / معلوماتي", "متوسط", "تتم معالجته بالتوثيق"),
        ]
        docs = [
            ("Initial_Assessment.pdf", "report", "تقييم الحالة الأولي", date(2026, 5, 14), [
                ("paragraph", "تقييم الحالة الحالية والأضرار في مجمع النور الصحي بحمص قبل وضع خطة التأهيل."),
                ("table", ["المجال", "ما يتطلبه قبل إعادة التشغيل"], [
                    ["الأجزاء الإنشائية", "التدعيم والإصلاح الإنشائي"],
                    ["الخدمات الكهربائية", "تأهيل الشبكة الكهربائية ولوحات التوزيع"],
                    ["الخدمات الميكانيكية", "المياه والصرف والخدمات"],
                    ["أنظمة السلامة", "أنظمة الإطفاء وإنذار الحريق"],
                ], [0.4, 0.6]),
            ]),
            ("Structural_Rehabilitation_Report.pdf", "report", "تقرير التدعيم والإصلاح الإنشائي", date(2026, 9, 27), [
                ("paragraph", "تقرير متابعة مرحلة التدعيم والإصلاح الإنشائي، ونسبة إنجازها 68%."),
                ("heading", "حدث بتاريخ 26/09/2026"),
                ("paragraph", "لوحظ تشقق إضافي في عنصر إنشائي في الطابق الثاني، الجناح الشرقي، أثناء إزالة طبقات الإكساء، ولم يكن ظاهراً في المعاينة الأولية. أُوقف العمل في المنطقة المتأثرة مؤقتاً، وحُوّلت الحالة إلى الفريق الهندسي لإجراء التقييم."),
            ]),
            ("Electrical_Assessment.pdf", "report", "تقييم الشبكة الكهربائية", date(2026, 9, 23), [
                ("paragraph", "تقييم الشبكة الكهربائية في المجمع ضمن مرحلة تأهيل الشبكة الكهربائية."),
                ("paragraph", "التمديدات الكهربائية القديمة خطر مرتفع قيد المعالجة."),
                ("heading", "اختبار لوحة التوزيع MDB-01"),
                ("paragraph", "ظهر خلل أثناء اختبار اللوحة بتاريخ 21/09/2026، وعولج بفصل الدارة وفحص اللوحة قبل إعادة الاختبار."),
            ]),
            ("Safety_Plan.pdf", "procedure", "خطة السلامة", date(2026, 6, 10), [
                ("paragraph", "إجراءات السلامة المعتمدة خلال أعمال إعادة التأهيل."),
                ("table", ["الإجراء"], [
                    ["تقييد الدخول إلى الأجزاء غير المستقرة من المبنى."],
                    ["إيقاف العمل عند ظهور أضرار إنشائية جديدة وإحالتها إلى الفريق الهندسي."],
                    ["فصل التغذية الكهربائية قبل العمل على اللوحات والدارات."],
                    ["إعادة تأهيل أنظمة الإطفاء وإنذار الحريق واختبارها قبل إعادة التشغيل."],
                ], [1.0]),
            ]),
            ("Rehabilitation_Progress_Report.pdf", "report", "تقرير تقدم إعادة التأهيل", date(2026, 9, 28), [
                ("heading", "حالة المراحل"),
                ("table", ["المرحلة", "الحالة", "الإنجاز"], phase_table(phases), [0.55, 0.25, 0.2]),
                ("heading", "سجل المخاطر"),
                ("table", ["الخطر", "النوع", "المستوى", "الحالة"], risks, [0.4, 0.22, 0.13, 0.25]),
            ]),
        ]
        for file_name, document_type, title, created, blocks in docs:
            add_document(project, file_name, document_type, title, blocks, samer, at(created.year, created.month, created.day))

    # -- 3. Damascus: in operation --------------------------------------------

    def _damascus(self):
        p = self.people
        admin, operations, officer = p["admin"], p["operations"], p["officer"]

        facility = saved(
            Facility(
                name=DAMASCUS_TOWER,
                type=Facility.Type.COMMERCIAL,
                location="دمشق - سوريا",
                operation_start_date=date(2025, 6, 1),
                status=Facility.Status.OPERATIONAL,
                created_by=admin,
            )
        )
        self._assign_facility(facility, with_security=True)

        project = saved(
            Project(
                name=DAMASCUS_TOWER,
                facility=facility,
                facility_type=Project.FacilityType.COMMERCIAL,
                location="دمشق - سوريا",
                latitude=Decimal("33.513800"),
                longitude=Decimal("36.276500"),
                start_date=date(2023, 3, 1),
                expected_completion_date=date(2025, 5, 15),
                actual_completion_date=date(2025, 5, 20),
                status=Project.Status.OPERATIONAL,
                description=(
                    "منشأة إدارية وتجارية مكتملة وقيد الاستخدام الفعلي، تستخدم لإظهار انتقال الرقابة "
                    "من مرحلة البناء إلى مراقبة التشغيل والأصول والتجهيزات والمخاطر والأحداث التي قد "
                    "تؤثر على الأشخاص أو استمرارية عمل المنشأة.\n\n"
                    "الاسم بالإنكليزية: Jasmine Business Center\n"
                    "النوع: منشأة تجارية وإدارية — عدد الطوابق: 12 — بدء التشغيل: 01/06/2025 — "
                    "الأولوية: تشغيلية مرتفعة"
                ),
                created_by=admin,
            )
        )
        facility.created_from_project = project
        saved(facility)
        self._assign_construction(project)
        add_phases(
            project,
            [
                ("الأعمال الإنشائية", date(2023, 3, 1), date(2024, 3, 31), "100", "completed", date(2023, 3, 1), date(2024, 3, 28), "critical"),
                ("الأعمال المعمارية والتشطيبات", date(2024, 2, 1), date(2025, 1, 31), "100", "completed", date(2024, 2, 1), date(2025, 1, 30), "high"),
                ("الأعمال الكهربائية والميكانيكية", date(2024, 4, 1), date(2025, 3, 15), "100", "completed", date(2024, 4, 1), date(2025, 3, 14), "high"),
                ("الاختبارات والتسليم", date(2025, 3, 16), date(2025, 5, 15), "100", "completed", date(2025, 3, 16), date(2025, 5, 20), "high"),
            ],
            admin,
        )

        installed, operating = date(2025, 5, 1), date(2025, 6, 1)
        assets = add_assets(
            facility,
            [
                ("JSM-ELEV-01", "المصعد رقم 1", "elevator", "نقل عمودي", "بهو الدخول", installed, operating, "operational", "92", "الأهمية: حرجة."),
                ("JSM-ELEV-02", "المصعد رقم 2", "elevator", "نقل عمودي", "بهو الدخول", installed, operating, "out_of_service", "60", "الأهمية: حرجة. يحتاج متابعة؛ أُوقف عن الخدمة بعد توقفه المفاجئ."),
                ("JSM-GEN-01", "المولد الاحتياطي", "generator", "كهربائية", "غرفة المولدات - القبو", installed, operating, "operational", "95", "الأهمية: حرجة."),
                ("JSM-MDB-01", "لوحة الكهرباء الرئيسية", "panel", "كهربائية", "غرفة الكهرباء الرئيسية - القبو", installed, operating, "operational", "78", "الأهمية: حرجة."),
                ("JSM-FP-01", "مضخة الحريق الرئيسية", "pump", "سلامة", "غرفة المضخات - القبو", installed, operating, "operational", "94", "الأهمية: حرجة."),
                ("JSM-UPS-01", "وحدة التغذية غير المنقطعة", "ups", "كهربائية", "غرفة الكهرباء الرئيسية - القبو", installed, operating, "operational", "90", "الأهمية: مرتفعة."),
                ("JSM-HVAC-01", "وحدة التكييف المركزية", "hvac", "تكييف وتبريد", "السطح", installed, operating, "operational", "88", "الأهمية: مرتفعة."),
                ("JSM-CCTV-01", "نظام المراقبة", "cctv", "أمن ومراقبة", "غرفة التحكم الأمني", installed, operating, "operational", "93", "الأهمية: مرتفعة."),
                ("JSM-FIRE-01", "نظام إنذار الحريق", "fire_alarm", "سلامة", "كامل المبنى", installed, operating, "operational", "96", "الأهمية: حرجة."),
                ("JSM-WT-01", "مضخة المياه", "pump", "خدمات", "غرفة المضخات - القبو", installed, operating, "operational", "89", "الأهمية: متوسطة."),
            ],
            admin,
        )

        # The main demo incident: elevator 2 stops. Left open, to resolve live.
        elevator = saved(
            Fault(
                asset=assets["JSM-ELEV-02"],
                fault_type="توقف مفاجئ",
                description=(
                    "توقف المصعد رقم 2 (ELEV-02) عن العمل أثناء التشغيل الطبيعي للمنشأة. الإجراء "
                    "الأولي: إيقاف المصعد عن الخدمة وإبلاغ فريق الصيانة."
                ),
                severity=Fault.Severity.MAJOR,
                discovery_time=at(2026, 9, 29, 10, 35),
                reported_by=operations,
                assigned_engineer=operations,
                status=Fault.Status.INVESTIGATING,
                created_by=operations,
            )
        )
        backdate(elevator, at(2026, 9, 29, 10, 35))

        panel = saved(
            Fault(
                asset=assets["JSM-MDB-01"],
                fault_type="ارتفاع حرارة",
                description=(
                    "تم تسجيل ارتفاع غير معتاد في درجة حرارة جزء من لوحة التوزيع الرئيسية MDB-01 "
                    "أثناء فترة التشغيل. الإجراء: تحويل الحالة للفريق الفني لفحص الأحمال والتوصيلات."
                ),
                severity=Fault.Severity.MAJOR,
                discovery_time=at(2026, 9, 30, 8, 50),
                reported_by=operations,
                status=Fault.Status.REPORTED,
                created_by=operations,
            )
        )
        backdate(panel, at(2026, 9, 30, 8, 50))

        # A smoke-detector alarm, recorded and closed. Entered manually: it
        # came from a detector in the building, not from the AI cameras.
        raised = at(2026, 9, 20, 14, 10)
        alert = saved(
            SecurityAlert(
                facility=facility,
                alert_type=SecurityAlert.AlertType.SMOKE,
                location="الطابق السادس",
                severity_level=SecurityAlert.Severity.CRITICAL,
                source=SecurityAlert.Source.MANUAL,
                status=SecurityAlert.Status.CONVERTED,
                reviewed_by=officer,
                review_notes="تم تسجيل إنذار من أحد كواشف الدخان في الطابق السادس، وتحويله إلى حادث.",
                created_by=officer,
            )
        )
        backdate(alert, raised)
        incident = saved(
            Incident(
                facility=facility,
                alert=alert,
                incident_type="دخان",
                description="تفعيل كاشف دخان في الطابق السادس: تم تسجيل إنذار من أحد كواشف الدخان.",
                location="الطابق السادس",
                severity_level=Incident.Severity.CRITICAL,
                assigned_to=officer,
                status=Incident.Status.CLOSED,
                final_report="تم التحقق من الموقع واتخاذ الإجراء وفق آلية السلامة المعتمدة.",
                closed_by=officer,
                closed_at=at(2026, 9, 20, 14, 45),
                created_by=officer,
            )
        )
        backdate(incident, at(2026, 9, 20, 14, 12))
        saved(
            IncidentAction(
                incident=incident,
                action_taken="التحقق من الموقع واتخاذ الإجراء وفق آلية السلامة المعتمدة.",
                taken_by=officer,
                taken_at=at(2026, 9, 20, 14, 15),
                completed_by=officer,
                completed_at=at(2026, 9, 20, 14, 40),
                created_by=officer,
            )
        )
