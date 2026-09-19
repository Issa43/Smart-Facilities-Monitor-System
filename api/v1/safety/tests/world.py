"""Synthetic multi-project Safety world for API tests (no live providers)."""

from decimal import Decimal
from types import SimpleNamespace

from apps.facilities.models import FacilityAssignment
from apps.projects.models import Project
from apps.safety.models import HazardEvent, ProjectSafetyAlert
from apps.safety.services import NormalizedHazardEvent, ingest_hazard_events
from apps.safety.tests.helpers import (
    CAIRO,
    NOW,
    assign_construction_manager,
    assign_operations_manager,
    enable_alerts,
    make_facility,
    make_project,
    make_user,
    offset_north,
    quake,
)
from apps.users.models import Role


TOKYO = (Decimal("35.676200"), Decimal("139.650300"))
PAYLOAD_MARKER = "PAYLOAD-MARKER-NOT-EXPOSED"


def build_world(settings, admin):
    enable_alerts(settings)
    facility_cairo = make_facility(admin, "Cairo Facility")
    facility_tokyo = make_facility(admin, "Tokyo Facility")

    construction = make_project(admin, name="Cairo construction")
    operational_cairo = make_project(
        admin,
        name="Cairo operations",
        status=Project.Status.OPERATIONAL,
        facility=facility_cairo,
        latitude=offset_north(CAIRO[0], 5),
    )
    operational_tokyo = make_project(
        admin,
        name="Tokyo operations",
        status=Project.Status.OPERATIONAL,
        facility=facility_tokyo,
        latitude=TOKYO[0],
        longitude=TOKYO[1],
    )
    make_project(admin, name="No coordinates", latitude=None, longitude=None)

    cm_cairo = make_user(Role.CONSTRUCTION_MANAGER, "cm-cairo")
    cm_tokyo = make_user(Role.CONSTRUCTION_MANAGER, "cm-tokyo")
    om_cairo = make_user(Role.OPERATIONS_MANAGER, "om-cairo")
    om_tokyo = make_user(Role.OPERATIONS_MANAGER, "om-tokyo")
    officer = make_user(Role.SECURITY_OFFICER, "so")
    assign_construction_manager(construction, cm_cairo, admin)
    assign_construction_manager(operational_tokyo, cm_tokyo, admin)
    assign_operations_manager(facility_cairo, om_cairo, admin)
    assign_operations_manager(facility_tokyo, om_tokyo, admin)
    FacilityAssignment.objects.create(
        facility=facility_cairo,
        user=officer,
        role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
        created_by=admin,
    )

    ingest_hazard_events(
        [
            quake(event_id="us-cairo", magnitude="6.0", distance_km=33),
            quake(
                event_id="us-tokyo",
                magnitude="6.8",
                latitude=offset_north(TOKYO[0], 20),
                longitude=TOKYO[1],
                payload={"place": PAYLOAD_MARKER, "token": "secret-token"},
            ),
            NormalizedHazardEvent(
                provider="gdacs",
                provider_event_id="FL:1000999",
                hazard_type="flood",
                title="Red flood alert (synthetic)",
                latitude=Decimal("35.700000"),
                longitude=Decimal("139.650000"),
                occurred_at=NOW,
                provider_updated_at=NOW,
                alert_level="red",
                source_url="https://www.gdacs.org/report.aspx?eventid=1000999&eventtype=FL",
                payload={"eventtype": "FL", "note": PAYLOAD_MARKER},
            ),
        ],
        now=NOW,
    )

    alerts = ProjectSafetyAlert.objects
    return SimpleNamespace(
        admin=admin,
        cm_cairo=cm_cairo,
        cm_tokyo=cm_tokyo,
        om_cairo=om_cairo,
        om_tokyo=om_tokyo,
        officer=officer,
        construction=construction,
        operational_cairo=operational_cairo,
        operational_tokyo=operational_tokyo,
        facility_cairo=facility_cairo,
        alert_construction=alerts.get(project=construction),
        alert_operational_cairo=alerts.get(project=operational_cairo),
        alert_tokyo_quake=alerts.get(project=operational_tokyo, hazard_type="earthquake"),
        alert_tokyo_flood=alerts.get(project=operational_tokyo, hazard_type="flood"),
        event_cairo=HazardEvent.objects.get(provider_event_id="us-cairo"),
        event_tokyo=HazardEvent.objects.get(provider_event_id="us-tokyo"),
        event_flood=HazardEvent.objects.get(provider_event_id="FL:1000999"),
    )
