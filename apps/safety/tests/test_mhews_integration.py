"""MHEWS end-to-end through the existing Safety pipeline (Phase 6C).

Proves an official Syrian warning reaches a ProjectSafetyAlert by exact polygon
containment, that the existing point/radius providers are unaffected, and that
the feature is dormant while its kill switch is off.
"""

from decimal import Decimal

import pytest

from apps.notifications.models import Notification
from apps.projects.models import Project
from apps.safety.models import HazardEvent, ProjectSafetyAlert
from apps.safety.providers import mhews
from apps.safety.services import ingest_hazard_events
from apps.safety.tests.helpers import (
    NOW,
    assign_construction_manager,
    enable_alerts,
    make_project,
    make_user,
    quake,
)
from apps.safety.tests.test_provider_mhews import SECOND_CAP, SQUARE_CAP, cap, reference_to
from apps.users.models import Role


pytestmark = pytest.mark.django_db

ROOT = "urn:oid:2.49.0.1.760.1.2026.8.14.13.42.0"
UPDATE_1 = "urn:oid:2.49.0.1.760.1.2026.8.21.19.10.0"
UPDATE_2 = "urn:oid:2.49.0.1.760.1.2026.9.2.17.56.0"


def events(*documents):
    return mhews.normalize_documents([mhews.parse_xml(d) for d in documents]).events


@pytest.fixture
def world(settings, super_admin_user):
    enable_alerts(settings)
    settings.SAFETY_WEATHER_ENABLED = True
    cm = make_user(Role.CONSTRUCTION_MANAGER, "cm")
    # Inside the CAP square (lat 35-36, lon 39-40).
    inside = make_project(
        super_admin_user,
        name="Inside warned area",
        latitude=Decimal("35.500000"),
        longitude=Decimal("39.500000"),
    )
    outside = make_project(
        super_admin_user,
        name="Outside warned area",
        latitude=Decimal("33.500000"),
        longitude=Decimal("38.000000"),
    )
    assign_construction_manager(inside, cm, super_admin_user)
    assign_construction_manager(outside, cm, super_admin_user)
    return {"admin": super_admin_user, "cm": cm, "inside": inside, "outside": outside}


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


def test_official_warning_creates_an_alert_only_for_contained_projects(world):
    result = ingest_hazard_events(events(cap(identifier=ROOT)), now=NOW)
    assert result.events_created == 1
    assert result.alerts_created == 1

    alert = ProjectSafetyAlert.objects.get()
    assert alert.project_id == world["inside"].pk
    assert alert.hazard_type == "flood"
    assert alert.severity == "critical"          # Severe -> red -> critical tier
    assert alert.status == ProjectSafetyAlert.Status.NEW
    assert alert.distance_km == Decimal("0.00")  # inside the warned area
    assert not ProjectSafetyAlert.objects.filter(project=world["outside"]).exists()


def test_a_project_outside_every_polygon_is_never_alerted(world):
    ingest_hazard_events(events(cap(polygons=(SECOND_CAP,))), now=NOW)
    # SECOND_CAP covers lat 33-34 / lon 36-37; neither project is inside.
    assert ProjectSafetyAlert.objects.count() == 0


def test_extreme_heat_and_dust_storm_warnings_reach_the_pipeline(world):
    ingest_hazard_events(events(cap(identifier=ROOT, event_code="OET-098")), now=NOW)
    ingest_hazard_events(events(cap(identifier=UPDATE_2, event_code="OET-170")), now=NOW)
    created = {alert.hazard_type for alert in ProjectSafetyAlert.objects.all()}
    assert created == {"extreme_heat", "dust_storm"}


def test_out_of_scope_codes_create_nothing(world):
    for code in ("OET-103", "OET-100"):
        ingest_hazard_events(events(cap(event_code=code)), now=NOW)
    assert HazardEvent.objects.count() == 0
    assert ProjectSafetyAlert.objects.count() == 0


def test_moderate_warning_uses_the_orange_tier(world):
    ingest_hazard_events(events(cap(identifier=ROOT, severity="Moderate")), now=NOW)
    alert = ProjectSafetyAlert.objects.get()
    assert alert.severity == "high"
    assert alert.recommended_action == "increase_precautions"


def test_minor_warning_is_green_and_matches_no_tier(world):
    result = ingest_hazard_events(events(cap(identifier=ROOT, severity="Minor")), now=NOW)
    assert result.alerts_created == 0
    assert ProjectSafetyAlert.objects.count() == 0


# ---------------------------------------------------------------------------
# CAP identity through ingestion
# ---------------------------------------------------------------------------


def test_update_chain_keeps_one_hazard_event(world):
    ingest_hazard_events(events(cap(identifier=ROOT)), now=NOW)
    ingest_hazard_events(
        events(cap(identifier=UPDATE_1, msg_type="Update", references=reference_to(ROOT))),
        now=NOW,
    )
    ingest_hazard_events(
        events(
            cap(identifier=ROOT),
            cap(identifier=UPDATE_1, msg_type="Update", references=reference_to(ROOT)),
            cap(identifier=UPDATE_2, msg_type="Update", references=reference_to(UPDATE_1)),
        ),
        now=NOW,
    )
    hazards = HazardEvent.objects.all()
    assert len(hazards) == 1
    assert hazards[0].provider_event_id == ROOT
    assert ProjectSafetyAlert.objects.count() == 1


def test_repeated_polling_of_the_same_document_is_idempotent(world):
    for _ in range(3):
        ingest_hazard_events(events(cap(identifier=ROOT)), now=NOW)
    assert HazardEvent.objects.count() == 1
    assert ProjectSafetyAlert.objects.count() == 1


def test_an_older_revision_never_rolls_the_hazard_backward(world):
    ingest_hazard_events(
        events(cap(identifier=ROOT, sent="2026-09-15T10:04:00+03:00", severity="Moderate")),
        now=NOW,
    )
    # An older Cancel arriving late must not withdraw the newer warning.
    ingest_hazard_events(
        events(
            cap(
                identifier=UPDATE_1,
                msg_type="Cancel",
                references=reference_to(ROOT),
                sent="2026-09-13T10:04:00+03:00",
            )
        ),
        now=NOW,
    )
    hazard = HazardEvent.objects.get()
    assert hazard.provider_status == HazardEvent.ProviderStatus.ACTIVE


def test_cancel_withdraws_the_existing_hazard_without_creating_a_new_one(world):
    ingest_hazard_events(events(cap(identifier=ROOT)), now=NOW)
    ingest_hazard_events(
        events(
            cap(
                identifier=UPDATE_1,
                msg_type="Cancel",
                references=reference_to(ROOT),
                # A real cancellation is a later provider revision.
                sent="2026-09-15T10:04:00+03:00",
            )
        ),
        now=NOW,
    )
    assert HazardEvent.objects.count() == 1
    hazard = HazardEvent.objects.get()
    assert hazard.provider_event_id == ROOT
    assert hazard.provider_status == HazardEvent.ProviderStatus.WITHDRAWN
    alert = ProjectSafetyAlert.objects.get()
    assert alert.hazard_withdrawn_at is not None
    # Withdrawal is advisory: the human workflow still owns the alert.
    assert alert.status == ProjectSafetyAlert.Status.NEW


# ---------------------------------------------------------------------------
# Kill switches and coexistence
# ---------------------------------------------------------------------------


def test_nothing_happens_while_the_safety_kill_switch_is_off(world, settings):
    settings.SAFETY_ALERTS_ENABLED = False
    result = ingest_hazard_events(events(cap(identifier=ROOT)), now=NOW)
    assert result.enabled is False
    assert HazardEvent.objects.count() == 0
    assert ProjectSafetyAlert.objects.count() == 0


def test_weather_provider_is_dormant_while_its_own_switch_is_off(settings):
    settings.SAFETY_WEATHER_ENABLED = False
    assert mhews.MhewsWarningProvider().enabled() is False


def test_mhews_coexists_with_point_radius_providers(world):
    """A polygon hazard and a USGS point hazard both work, independently."""

    ingest_hazard_events(events(cap(identifier=ROOT)), now=NOW)
    ingest_hazard_events(
        [quake(magnitude="6.5", latitude=Decimal("35.500000"), longitude=Decimal("39.500000"))],
        now=NOW,
    )
    providers = {hazard.provider for hazard in HazardEvent.objects.all()}
    assert providers == {"mhews", "usgs"}
    alerts = ProjectSafetyAlert.objects.filter(project=world["inside"])
    assert {alert.hazard_type for alert in alerts} == {"flood", "earthquake"}
    # The earthquake alert carries a real measured distance; the weather alert
    # carries 0.00 because the project is inside the warned area.
    by_type = {alert.hazard_type: alert.distance_km for alert in alerts}
    assert by_type["flood"] == Decimal("0.00")
    assert by_type["earthquake"] >= Decimal("0.00")


def test_existing_safety_notifications_are_reused(world, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        ingest_hazard_events(events(cap(identifier=ROOT)), now=NOW)
    notifications = Notification.objects.filter(recipient=world["cm"])
    assert notifications.count() == 1
    assert notifications.first().category == Notification.Category.SAFETY


def test_ingestion_never_actions_an_alert(world):
    ingest_hazard_events(events(cap(identifier=ROOT)), now=NOW)
    alert = ProjectSafetyAlert.objects.get()
    assert alert.status == ProjectSafetyAlert.Status.NEW
    assert alert.decided_by_id is None
    assert alert.decided_at is None
