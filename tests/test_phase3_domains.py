from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
import unittest

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.assets.models import Asset
from apps.assets.services import transition_asset_status
from apps.attachments.access import (
    ProtectedAttachmentAccessDenied,
    authorize_attachment_download,
    authorize_protected_file_download,
)
from apps.attachments.models import Attachment
from apps.construction.models import DailyReport
from apps.facilities.models import Facility, FacilityAssignment
from apps.maintenance.models import Fault, MaintenanceOrder
from apps.maintenance.services import (
    begin_fault_investigation,
    close_fault,
    close_maintenance_order,
    complete_maintenance_order,
    resolve_fault,
    start_maintenance_order,
)
from apps.materials.models import Material, MaterialConsumptionRecord, MaterialRequest
from apps.materials.services import (
    approve_material_request,
    consume_material,
    fulfill_material_request,
    review_material_request,
)
from apps.projects.models import Project, ProjectAssignment, ProjectPhase
from apps.projects.services import (
    approve_phase,
    calculate_project_progress,
    complete_project,
    convert_project_to_facility,
    record_phase_progress,
    reject_phase,
    start_project,
)
from apps.reports.models import Report
from apps.reports.services import (
    create_report_request,
    create_report_template,
    generate_report,
    validate_template_configuration,
)
from apps.security.models import Incident, IncidentAction, SecurityAlert
from apps.security.services import (
    close_incident,
    convert_alert_to_incident,
    record_incident_action,
    review_security_alert,
    start_incident_investigation,
)
from apps.users.models import Role, User


class Phase3DomainTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_role, _ = Role.objects.get_or_create(
            name=Role.SUPER_ADMIN, defaults={"description": "Admin"}
        )
        cls.manager_role, _ = Role.objects.get_or_create(
            name=Role.CONSTRUCTION_MANAGER, defaults={"description": "Manager"}
        )
        cls.security_role, _ = Role.objects.get_or_create(
            name=Role.SECURITY_OFFICER, defaults={"description": "Security"}
        )
        cls.admin = User.objects.create_user(
            email="phase3-admin@example.com",
            username="phase3-admin",
            full_name="Phase 3 Admin",
            password="StrongPass123!",
            role=cls.admin_role,
        )
        cls.manager = User.objects.create_user(
            email="phase3-manager@example.com",
            username="phase3-manager",
            full_name="Phase 3 Manager",
            password="StrongPass123!",
            role=cls.manager_role,
        )
        cls.security_user = User.objects.create_user(
            email="phase3-security@example.com",
            username="phase3-security",
            full_name="Phase 3 Security",
            password="StrongPass123!",
            role=cls.security_role,
        )

    def make_project(self, *, status=Project.Status.PLANNING):
        today = date.today()
        return Project.objects.create(
            name="Test Project",
            facility_type=Project.FacilityType.COMMERCIAL,
            location="Cairo",
            start_date=today,
            expected_completion_date=today + timedelta(days=30),
            actual_completion_date=today if status == Project.Status.COMPLETED else None,
            status=status,
            created_by=self.admin,
        )

    def make_phase(self, project, *, status=ProjectPhase.Status.NOT_STARTED):
        today = date.today()
        progress = Decimal("100.00") if status == ProjectPhase.Status.COMPLETED else Decimal("0.00")
        return ProjectPhase.objects.create(
            project=project,
            name="Foundation",
            sequence_number=1,
            start_date=today,
            expected_completion_date=today + timedelta(days=10),
            actual_start_date=today if progress else None,
            actual_completion_date=today if status == ProjectPhase.Status.COMPLETED else None,
            current_progress=progress,
            status=status,
            approved_by=self.admin if status == ProjectPhase.Status.COMPLETED else None,
            approved_at=(timezone.now() if status == ProjectPhase.Status.COMPLETED else None),
            created_by=self.manager,
        )

    def make_facility(self):
        return Facility.objects.create(
            name="Operational Facility",
            type=Facility.Type.COMMERCIAL,
            location="Cairo",
            created_by=self.admin,
        )

    def make_asset(self):
        return Asset.objects.create(
            facility=self.make_facility(),
            name="Pump",
            asset_type="Mechanical",
            category="Pump",
            serial_number=f"SER-{Asset.objects.count()}",
            manufacturer="Maker",
            model="P1",
            location_inside_facility="Plant room",
            installation_date=date.today(),
            created_by=self.admin,
        )

    def test_project_lifecycle_progress_and_facility_conversion(self):
        project = self.make_project()
        phase = self.make_phase(project)
        ProjectAssignment.objects.create(
            project=project,
            user=self.manager,
            role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
            created_by=self.admin,
        )
        ProjectAssignment.objects.create(
            project=project,
            user=self.manager,
            role_type=ProjectAssignment.RoleType.VIEWER,
            created_by=self.admin,
        )
        authorize_protected_file_download(self.manager, project)
        with self.assertRaises(ProtectedAttachmentAccessDenied):
            authorize_protected_file_download(self.security_user, project)
        start_project(project_id=project.pk)
        record_phase_progress(
            phase_id=phase.pk,
            progress_percentage="100.00",
            work_completed="Finished",
            actor=self.manager,
        )
        approve_phase(phase_id=phase.pk, actor=self.admin)
        self.assertEqual(calculate_project_progress(project), Decimal("100.00"))
        complete_project(project_id=project.pk, actual_completion_date=date.today())
        facility = convert_project_to_facility(project_id=project.pk, actor=self.admin)
        project.refresh_from_db()
        self.assertEqual(project.status, Project.Status.OPERATIONAL)
        self.assertEqual(project.facility_id, facility.pk)
        self.assertEqual(facility.created_from_project_id, project.pk)
        with self.assertRaises(ValidationError):
            convert_project_to_facility(project_id=project.pk, actor=self.admin)

    def test_invalid_completion_and_phase_rejection(self):
        project = self.make_project(status=Project.Status.IN_PROGRESS)
        phase = self.make_phase(project, status=ProjectPhase.Status.IN_PROGRESS)
        with self.assertRaises(ValidationError):
            complete_project(project_id=project.pk, actual_completion_date=date.today())
        review = reject_phase(phase_id=phase.pk, actor=self.admin, reason="Unsafe")
        phase.refresh_from_db()
        self.assertEqual(phase.status, ProjectPhase.Status.REJECTED)
        self.assertEqual(review.reason, "Unsafe")

    def test_material_constraints_consumption_and_request_lifecycle(self):
        project = self.make_project()
        material = Material.objects.create(
            project=project,
            name="Cement",
            unit=Material.Unit.BAG,
            quantity_required=Decimal("10.000"),
            quantity_used=Decimal("0.000"),
            quantity_remaining=Decimal("10.000"),
            min_stock_threshold=Decimal("2.000"),
            created_by=self.manager,
        )
        request = MaterialRequest.objects.create(
            project=project,
            material=material,
            quantity_requested=Decimal("4.000"),
            reason="Required",
            priority=MaterialRequest.Priority.HIGH,
            created_by=self.manager,
        )
        review_material_request(request.pk)
        approve_material_request(request.pk, actor=self.admin)
        fulfill_material_request(request.pk)
        request.refresh_from_db()
        material.refresh_from_db()
        self.assertEqual(request.status, MaterialRequest.Status.COMPLETED)
        self.assertEqual(material.quantity_remaining, Decimal("10.000"))
        consume_material(material_id=material.pk, quantity="3.250", actor=self.manager)
        material.refresh_from_db()
        self.assertEqual(material.quantity_used, Decimal("3.250"))
        self.assertEqual(material.quantity_remaining, Decimal("6.750"))
        self.assertEqual(MaterialConsumptionRecord.objects.count(), 1)
        with self.assertRaises(ValidationError):
            consume_material(material_id=material.pk, quantity="7.000", actor=self.manager)

    def test_operations_lifecycles_keep_asset_consistent(self):
        asset = self.make_asset()
        transition_asset_status(
            asset_id=asset.pk, target_status=Asset.Status.UNDER_MAINTENANCE
        )
        with self.assertRaises(ValidationError):
            transition_asset_status(
                asset_id=asset.pk, target_status=Asset.Status.UNDER_MAINTENANCE
            )
        order = MaintenanceOrder.objects.create(
            asset=asset,
            type=MaintenanceOrder.Type.CORRECTIVE,
            description="Repair",
            reason="Failure",
            expected_execution_date=date.today(),
            created_by=self.admin,
        )
        start_maintenance_order(order_id=order.pk)
        complete_maintenance_order(order_id=order.pk, actual_completion_date=date.today())
        close_maintenance_order(order_id=order.pk)
        fault = Fault.objects.create(
            asset=asset,
            fault_type="Leak",
            description="Seal leak",
            severity=Fault.Severity.MODERATE,
            reported_by=self.admin,
            created_by=self.admin,
        )
        begin_fault_investigation(fault_id=fault.pk, assigned_engineer=self.manager)
        resolve_fault(fault_id=fault.pk, root_cause="Seal", resolution="Replaced")
        close_fault(fault_id=fault.pk)
        asset.refresh_from_db()
        self.assertEqual(asset.current_status, Asset.Status.OPERATIONAL)

    def test_security_lifecycle_duplicate_conversion_and_action_closure_rule(self):
        facility = self.make_facility()
        FacilityAssignment.objects.create(
            facility=facility,
            user=self.security_user,
            role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
            created_by=self.admin,
        )
        alert = SecurityAlert.objects.create(
            facility=facility,
            alert_type=SecurityAlert.AlertType.INTRUSION,
            location="Gate",
            severity_level=SecurityAlert.Severity.HIGH,
            source=SecurityAlert.Source.MANUAL,
            created_by=self.security_user,
        )
        review_security_alert(alert_id=alert.pk, actor=self.security_user)
        authorize_protected_file_download(self.security_user, alert)
        with self.assertRaises(ProtectedAttachmentAccessDenied):
            authorize_protected_file_download(self.manager, alert)
        incident = convert_alert_to_incident(
            alert_id=alert.pk,
            actor=self.security_user,
            incident_type="Intrusion",
            description="Unauthorized access",
        )
        with self.assertRaises(ValidationError):
            convert_alert_to_incident(
                alert_id=alert.pk,
                actor=self.security_user,
                incident_type="Intrusion",
                description="Duplicate",
            )
        action = record_incident_action(
            incident_id=incident.pk,
            actor=self.security_user,
            action_taken="Secured gate",
        )
        action.notes = "Changed"
        with self.assertRaises(ValidationError):
            action.save()
        start_incident_investigation(incident_id=incident.pk)
        close_incident(
            incident_id=incident.pk,
            actor=self.security_user,
            final_report="Resolved",
        )
        with self.assertRaises(ValidationError):
            record_incident_action(
                incident_id=incident.pk,
                actor=self.security_user,
                action_taken="Late action",
            )

    def test_reports_generate_domain_pdf_and_xlsx_with_protected_access(self):
        project = self.make_project()
        Material.objects.create(
            project=project,
            name="Steel",
            unit=Material.Unit.KILOGRAM,
            quantity_required=Decimal("5.000"),
            quantity_used=Decimal("0.000"),
            quantity_remaining=Decimal("5.000"),
            min_stock_threshold=Decimal("1.000"),
            created_by=self.manager,
        )
        with self.assertRaises(ValidationError):
            validate_template_configuration({"columns": ["name", "name"]})

        generated = []
        for report_format in (Report.Format.PDF, Report.Format.EXCEL):
            template = create_report_template(
                name=f"Materials {report_format}",
                module=Report.Module.MATERIALS,
                report_format=report_format,
                configuration={"columns": ["name", "quantity_remaining"]},
                actor=self.admin,
            )
            report = create_report_request(
                report_type="Inventory",
                module=Report.Module.MATERIALS,
                report_format=report_format,
                parameters={"project_id": str(project.pk)},
                actor=self.manager,
                template_id=template.pk,
            )
            report = generate_report(report_id=report.pk)
            generated.append(report)
            self.assertEqual(report.status, Report.Status.COMPLETED)
            self.assertTrue(report.file_path.storage.exists(report.file_path.name))
            authorize_protected_file_download(self.manager, report)
            with self.assertRaises(ProtectedAttachmentAccessDenied):
                authorize_protected_file_download(self.security_user, report)

        for report in generated:
            report.file_path.storage.delete(report.file_path.name)

    def test_attachment_metadata_and_project_scope_access(self):
        project = self.make_project()
        phase = self.make_phase(project)
        ProjectAssignment.objects.create(
            project=project,
            user=self.manager,
            role_type=ProjectAssignment.RoleType.VIEWER,
            created_by=self.admin,
        )
        upload = SimpleUploadedFile(
            "evidence.pdf", b"%PDF-1.4\n%%EOF\n", content_type="text/plain"
        )
        attachment = Attachment(
            entity_type="project_phase",
            entity_id=phase.pk,
            file=upload,
            original_file_name="forged.txt",
            file_type="txt",
            mime_type="text/plain",
            file_size=1,
            created_by=self.manager,
        )
        attachment.save()
        self.assertEqual(attachment.original_file_name, "evidence.pdf")
        self.assertEqual(attachment.file_type, "pdf")
        self.assertEqual(attachment.mime_type, "application/pdf")
        authorize_attachment_download(self.manager, attachment)
        with self.assertRaises(ProtectedAttachmentAccessDenied):
            authorize_attachment_download(self.security_user, attachment)
        attachment.file.storage.delete(attachment.file.name)

    def test_user_delete_deactivates_and_preserves_history(self):
        project = self.make_project()
        DailyReport.objects.create(
            project=project,
            report_date=date.today(),
            weather_condition="Clear",
            workers_count=1,
            report_content="Work",
            created_by=self.manager,
        )
        user_id = self.manager.pk
        self.manager.delete()
        preserved = User.objects.get(pk=user_id)
        self.assertEqual(preserved.status, User.STATUS_INACTIVE)
        self.assertTrue(DailyReport.all_objects.filter(created_by_id=user_id).exists())


class MaterialConcurrencyTests(TransactionTestCase):
    reset_sequences = False

    @unittest.skipIf(connection.vendor == "sqlite", "Requires PostgreSQL row-level locking")
    def test_concurrent_consumption_cannot_overdraw_stock(self):
        role, _ = Role.objects.get_or_create(name=Role.SUPER_ADMIN)
        actor = User.objects.create_user(
            email="stock@example.com",
            username="stock-user",
            full_name="Stock User",
            password="StrongPass123!",
            role=role,
        )
        project = Project.objects.create(
            name="Stock Project",
            facility_type=Project.FacilityType.INDUSTRIAL,
            location="Cairo",
            start_date=date.today(),
            expected_completion_date=date.today() + timedelta(days=1),
            created_by=actor,
        )
        material = Material.objects.create(
            project=project,
            name="Cable",
            unit=Material.Unit.METRE,
            quantity_required=Decimal("10.000"),
            quantity_used=Decimal("0.000"),
            quantity_remaining=Decimal("10.000"),
            min_stock_threshold=Decimal("1.000"),
            created_by=actor,
        )

        def consume():
            close_old_connections()
            try:
                consume_material(material_id=material.pk, quantity="7.000", actor=actor)
                return "ok"
            except ValidationError:
                return "rejected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _index: consume(), range(2)))

        self.assertCountEqual(outcomes, ["ok", "rejected"])
        material.refresh_from_db()
        self.assertEqual(material.quantity_remaining, Decimal("3.000"))
        self.assertEqual(MaterialConsumptionRecord.objects.count(), 1)
