"""Synthetic builders for safety tests. No live provider data is used."""

import uuid
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from apps.common.models import SystemSetting
from apps.facilities.models import Facility, FacilityAssignment
from apps.projects.models import Project, ProjectAssignment
from apps.safety.services import NormalizedHazardEvent
from apps.users.models import User

from conftest import seeded_role


NOW = datetime(2026, 9, 15, 12, 0, tzinfo=dt_timezone.utc)
CAIRO = (Decimal("30.044400"), Decimal("31.235700"))


def make_user(role_name, label, *, status=User.STATUS_ACTIVE):
    suffix = uuid.uuid4().hex[:8]
    return User.objects.create_user(
        email=f"{label}-{suffix}@sflms.test",
        username=f"{label}-{suffix}",
        full_name=f"{label} {suffix}",
        password="StrongPass123!",
        role=seeded_role(role_name),
        status=status,
    )


def make_facility(actor, name="Cairo Facility"):
    return Facility.objects.create(
        name=name,
        type=Facility.Type.COMMERCIAL,
        location="Cairo",
        created_by=actor,
    )


def make_project(
    actor,
    *,
    name="Cairo Tower",
    latitude=CAIRO[0],
    longitude=CAIRO[1],
    status=Project.Status.IN_PROGRESS,
    facility=None,
):
    extra = {}
    if status in {Project.Status.COMPLETED, Project.Status.OPERATIONAL}:
        extra["actual_completion_date"] = date(2026, 6, 1)
    return Project.objects.create(
        name=name,
        facility=facility,
        facility_type=Project.FacilityType.COMMERCIAL,
        location="Cairo",
        latitude=latitude,
        longitude=longitude,
        start_date=date(2026, 1, 1),
        expected_completion_date=date(2027, 1, 1),
        status=status,
        created_by=actor,
        **extra,
    )


def assign_construction_manager(project, user, actor):
    return ProjectAssignment.objects.create(
        project=project,
        user=user,
        role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
        created_by=actor,
    )


def assign_operations_manager(facility, user, actor):
    return FacilityAssignment.objects.create(
        facility=facility,
        user=user,
        role_type=FacilityAssignment.RoleType.OPERATIONS_MANAGER,
        created_by=actor,
    )


def set_setting(key, value):
    setting, _ = SystemSetting.objects.update_or_create(key=key, defaults={"value": value})
    return setting


def enable_alerts(settings):
    settings.SAFETY_ALERTS_ENABLED = True
    set_setting("safety.externalAlerts", True)


def offset_north(latitude, kilometres):
    """Latitude shifted north by roughly ``kilometres`` along a meridian."""

    return (Decimal(str(latitude)) + Decimal(str(kilometres / 111.195))).quantize(
        Decimal("0.000001")
    )


def quake(
    *,
    event_id="us-synthetic-1",
    magnitude="6.0",
    latitude=None,
    longitude=None,
    distance_km=33,
    occurred_at=NOW,
    updated_at=NOW,
    status="active",
    **overrides,
):
    lat = latitude if latitude is not None else offset_north(CAIRO[0], distance_km)
    lon = longitude if longitude is not None else CAIRO[1]
    values = {
        "provider": "usgs",
        "provider_event_id": event_id,
        "hazard_type": "earthquake",
        "title": f"M {magnitude} - synthetic test event",
        "latitude": lat,
        "longitude": lon,
        "occurred_at": occurred_at,
        "provider_updated_at": updated_at,
        "magnitude": Decimal(magnitude) if magnitude is not None else None,
        "provider_severity": f"M{magnitude}",
        "source_url": f"https://earthquake.usgs.gov/earthquakes/eventpage/{event_id}",
        "provider_status": status,
        "payload": {"mag": magnitude, "place": "synthetic"},
    }
    values.update(overrides)
    return NormalizedHazardEvent(**values)


def later(minutes):
    return NOW + timedelta(minutes=minutes)
