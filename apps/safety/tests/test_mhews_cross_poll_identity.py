"""Cross-poll CAP identity (Phase 6C.1).

Each `poll()` here is a separate ingestion call containing only the documents
that cycle's feed would expose. The root Alert is deliberately absent from the
later polls, which is the case Phase 6C could not resolve.
"""

from decimal import Decimal

import pytest

from apps.safety.models import HazardEvent, HazardEventAlias, ProjectSafetyAlert
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
from apps.safety.tests.test_provider_mhews import cap, reference_to
from apps.users.models import Role


pytestmark = pytest.mark.django_db

ROOT = "urn:oid:2.49.0.1.760.1.2026.8.14.13.42.0"
UPDATE_1 = "urn:oid:2.49.0.1.760.1.2026.8.21.19.10.0"
UPDATE_2 = "urn:oid:2.49.0.1.760.1.2026.9.2.17.56.0"
UNKNOWN = "urn:oid:2.49.0.1.760.1.2026.1.1.0.0.0"

T1 = "2026-09-14T10:04:00+03:00"
T2 = "2026-09-15T10:04:00+03:00"
T3 = "2026-09-16T10:04:00+03:00"
T_BETWEEN = "2026-09-14T18:00:00+03:00"  # after T1, before T2


def poll(*documents):
    """One polling cycle: only these documents are visible to the adapter."""

    events = mhews.normalize_documents([mhews.parse_xml(d) for d in documents]).events
    return ingest_hazard_events(events, now=NOW)


@pytest.fixture
def world(settings, super_admin_user):
    enable_alerts(settings)
    settings.SAFETY_WEATHER_ENABLED = True
    cm = make_user(Role.CONSTRUCTION_MANAGER, "cm")
    project = make_project(
        super_admin_user,
        name="Inside warned area",
        latitude=Decimal("35.500000"),
        longitude=Decimal("39.500000"),
    )
    assign_construction_manager(project, cm, super_admin_user)
    return {"admin": super_admin_user, "cm": cm, "project": project}


def only_hazard():
    hazards = list(HazardEvent.all_objects.all())
    assert len(hazards) == 1, [h.provider_event_id for h in hazards]
    return hazards[0]


# ---------------------------------------------------------------------------
# The primary regression: the root is gone from the later feed
# ---------------------------------------------------------------------------


def test_late_update_without_the_root_in_the_feed_reuses_the_hazard(world):
    poll(cap(identifier=ROOT, sent=T1))
    hazard_id = only_hazard().pk

    # Poll 2 exposes only the Update; the Alert has aged out of the feed.
    poll(cap(identifier=UPDATE_1, msg_type="Update", references=reference_to(ROOT), sent=T2))

    hazard = only_hazard()
    assert hazard.pk == hazard_id
    assert hazard.provider_event_id == ROOT
    assert hazard.revision == 2
    assert ProjectSafetyAlert.objects.count() == 1


def test_update_of_update_across_three_separate_polls_keeps_one_hazard(world):
    poll(cap(identifier=ROOT, sent=T1))
    hazard_id = only_hazard().pk
    poll(cap(identifier=UPDATE_1, msg_type="Update", references=reference_to(ROOT), sent=T2))
    # Poll 3 references UPDATE_1, which is itself no longer in the feed.
    poll(cap(identifier=UPDATE_2, msg_type="Update", references=reference_to(UPDATE_1), sent=T3))

    hazard = only_hazard()
    assert hazard.pk == hazard_id
    assert hazard.provider_event_id == ROOT
    assert hazard.revision == 3
    assert ProjectSafetyAlert.objects.count() == 1


def test_late_cancel_without_the_root_withdraws_the_existing_hazard(world):
    poll(cap(identifier=ROOT, sent=T1))
    hazard_id = only_hazard().pk

    poll(cap(identifier=UPDATE_1, msg_type="Cancel", references=reference_to(ROOT), sent=T2))

    hazard = only_hazard()
    assert hazard.pk == hazard_id
    assert hazard.provider_status == HazardEvent.ProviderStatus.WITHDRAWN
    alert = ProjectSafetyAlert.objects.get()
    assert alert.hazard_withdrawn_at is not None
    assert alert.status == ProjectSafetyAlert.Status.NEW


def test_cancel_after_a_two_hop_chain_resolves_to_the_original_hazard(world):
    poll(cap(identifier=ROOT, sent=T1))
    poll(cap(identifier=UPDATE_1, msg_type="Update", references=reference_to(ROOT), sent=T2))
    poll(cap(identifier=UPDATE_2, msg_type="Cancel", references=reference_to(UPDATE_1), sent=T3))

    hazard = only_hazard()
    assert hazard.provider_event_id == ROOT
    assert hazard.provider_status == HazardEvent.ProviderStatus.WITHDRAWN


# ---------------------------------------------------------------------------
# Idempotency and ordering
# ---------------------------------------------------------------------------


def test_repeating_the_same_revision_across_polls_is_idempotent(world):
    poll(cap(identifier=ROOT, sent=T1))
    for _ in range(3):
        poll(cap(identifier=UPDATE_1, msg_type="Update", references=reference_to(ROOT), sent=T2))

    hazard = only_hazard()
    assert hazard.revision == 2
    assert ProjectSafetyAlert.objects.count() == 1


def test_an_older_revision_arriving_late_does_not_roll_back_or_duplicate(world):
    poll(cap(identifier=ROOT, sent=T1, severity="Moderate"))
    poll(
        cap(
            identifier=UPDATE_1,
            msg_type="Update",
            references=reference_to(ROOT),
            sent=T2,
            severity="Severe",
        )
    )
    # An older Update overtaken in transit.
    poll(
        cap(
            identifier=UPDATE_2,
            msg_type="Update",
            references=reference_to(ROOT),
            sent=T_BETWEEN,
            severity="Minor",
        )
    )

    hazard = only_hazard()
    assert hazard.provider_event_id == ROOT
    assert hazard.alert_level == "red"          # the T2 revision still stands
    assert hazard.provider_severity == "Severe"
    assert hazard.revision == 2


# ---------------------------------------------------------------------------
# Fail-closed cases
# ---------------------------------------------------------------------------


def test_update_referencing_an_unknown_root_creates_nothing(world):
    result = poll(
        cap(identifier=UPDATE_1, msg_type="Update", references=reference_to(UNKNOWN), sent=T2)
    )
    assert HazardEvent.all_objects.count() == 0
    assert ProjectSafetyAlert.objects.count() == 0
    assert result.events_ignored == 1


def test_cancel_referencing_an_unknown_root_creates_nothing(world):
    poll(cap(identifier=UPDATE_1, msg_type="Cancel", references=reference_to(UNKNOWN), sent=T2))
    assert HazardEvent.all_objects.count() == 0
    assert ProjectSafetyAlert.objects.count() == 0


def test_an_update_with_no_references_at_all_creates_nothing(world):
    poll(cap(identifier=UPDATE_1, msg_type="Update", sent=T2))
    assert HazardEvent.all_objects.count() == 0


def test_a_cyclic_reference_chain_fails_closed(world):
    """A references B and B references A: neither may invent a hazard."""

    poll(
        cap(identifier=ROOT, msg_type="Update", references=reference_to(UPDATE_1), sent=T1),
        cap(identifier=UPDATE_1, msg_type="Update", references=reference_to(ROOT), sent=T2),
    )
    assert HazardEvent.all_objects.count() == 0


def test_references_from_an_unapproved_sender_cannot_claim_an_identity(world):
    poll(cap(identifier=ROOT, sent=T1))
    hazard_id = only_hazard().pk
    poll(
        cap(
            identifier=UPDATE_1,
            msg_type="Update",
            references=f"attacker@example.com,{ROOT},2026-08-21T19:10:00-00:00",
            sent=T2,
        )
    )
    # The forged reference is ignored, so this resolves to nothing and is
    # dropped rather than hijacking or duplicating the real hazard.
    assert only_hazard().pk == hazard_id
    assert only_hazard().revision == 1


# ---------------------------------------------------------------------------
# Aliases and provider isolation
# ---------------------------------------------------------------------------


def test_every_chain_identifier_is_recorded_once_and_never_reassigned(world):
    poll(cap(identifier=ROOT, sent=T1))
    poll(cap(identifier=UPDATE_1, msg_type="Update", references=reference_to(ROOT), sent=T2))
    poll(cap(identifier=UPDATE_2, msg_type="Update", references=reference_to(UPDATE_1), sent=T3))

    aliases = HazardEventAlias.all_objects.filter(provider="mhews")
    assert {alias.alias_identifier for alias in aliases} == {ROOT, UPDATE_1, UPDATE_2}
    assert {alias.hazard_event_id for alias in aliases} == {only_hazard().pk}


def test_same_batch_resolution_from_phase_6c_still_works(world):
    """The whole chain in one poll must still collapse to one hazard."""

    poll(
        cap(identifier=ROOT, sent=T1),
        cap(identifier=UPDATE_1, msg_type="Update", references=reference_to(ROOT), sent=T2),
        cap(identifier=UPDATE_2, msg_type="Update", references=reference_to(UPDATE_1), sent=T3),
    )
    assert only_hazard().provider_event_id == ROOT
    assert ProjectSafetyAlert.objects.count() == 1


def test_point_identifier_providers_record_no_aliases(world):
    """USGS keeps one stable identifier per event and is unaffected."""

    ingest_hazard_events(
        [quake(magnitude="6.5", latitude=Decimal("35.500000"), longitude=Decimal("39.500000"))],
        now=NOW,
    )
    assert HazardEvent.all_objects.filter(provider="usgs").count() == 1
    assert HazardEventAlias.all_objects.filter(provider="usgs").count() == 0


def test_an_alias_never_crosses_providers(world):
    poll(cap(identifier=ROOT, sent=T1))
    hazard = only_hazard()
    # The same identifier string under a different provider is a different key.
    HazardEventAlias.all_objects.create(
        provider="gdacs", alias_identifier=ROOT, hazard_event=hazard
    )
    assert (
        HazardEventAlias.all_objects.filter(alias_identifier=ROOT).count() == 2
    )
