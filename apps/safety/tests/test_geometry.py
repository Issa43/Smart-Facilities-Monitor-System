"""Polygon / MultiPolygon area geometry (Phase 6B).

Covers the new area-matching mode and proves the existing point/radius mode is
unchanged and can coexist with it. Positions are ``[longitude, latitude]``.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.projects.models import Project
from apps.safety import geo
from apps.safety.models import HazardEvent
from apps.safety.tests.helpers import make_project, make_user
from apps.users.models import Role


# A 2x2 degree square with its south-west corner at (lon 10, lat 20).
SQUARE = [[[10.0, 20.0], [12.0, 20.0], [12.0, 22.0], [10.0, 22.0], [10.0, 20.0]]]
# The same square with a 0.4 degree hole around (11, 21).
SQUARE_WITH_HOLE = [
    SQUARE[0],
    [[10.8, 20.8], [11.2, 20.8], [11.2, 21.2], [10.8, 21.2], [10.8, 20.8]],
]
# An L shape: a point can sit inside its bounding box yet outside the polygon.
L_SHAPE = [[[0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [1.0, 1.0], [1.0, 2.0], [0.0, 2.0], [0.0, 0.0]]]
FAR_SQUARE = [[[50.0, 60.0], [52.0, 60.0], [52.0, 62.0], [50.0, 62.0], [50.0, 60.0]]]


def inside(latitude, longitude, polygons):
    return geo.point_in_multipolygon(latitude, longitude, geo.normalize_multipolygon(polygons))


# ---------------------------------------------------------------------------
# Normalization, coordinate order and validation
# ---------------------------------------------------------------------------


def test_polygon_coordinates_are_promoted_to_multipolygon():
    normalized = geo.normalize_multipolygon(SQUARE)
    assert normalized == [SQUARE]
    assert geo.normalize_multipolygon([SQUARE]) == [SQUARE]


def test_unclosed_rings_are_closed_and_stored_canonically():
    normalized = geo.normalize_multipolygon([[[10.0, 20.0], [12.0, 20.0], [12.0, 22.0]]])
    ring = normalized[0][0]
    assert ring[0] == ring[-1] == [10.0, 20.0]
    assert len(ring) == 4


def test_coordinates_are_longitude_latitude_not_the_reverse():
    # (lon 11, lat 21) is inside the square; the swapped pair is not a valid
    # position at all, because latitude 11 with longitude 21 falls outside it.
    assert inside(21.0, 11.0, SQUARE) is True
    assert inside(11.0, 21.0, SQUARE) is False
    # A swapped pair with latitude beyond 90 is rejected outright.
    with pytest.raises(geo.InvalidGeometry):
        geo.normalize_multipolygon([[[20.0, 100.0], [22.0, 100.0], [22.0, 102.0], [20.0, 100.0]]])


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        "polygon",
        [[]],
        [[[]]],
        [[[10.0, 20.0], [12.0, 20.0]]],
        [[[10.0, 20.0], [10.0, 20.0], [10.0, 20.0]]],
        [[[10.0, 20.0], [12.0, 20.0], ["x", 22.0], [10.0, 20.0]]],
        [[[10.0, 20.0], [12.0, 20.0], [None, 22.0], [10.0, 20.0]]],
        [[[10.0, 20.0], [12.0, 20.0], [float("nan"), 22.0], [10.0, 20.0]]],
        [[[10.0, 20.0], [12.0, 20.0], [float("inf"), 22.0], [10.0, 20.0]]],
        [[[10.0, 20.0], [12.0, 20.0], [200.0, 22.0], [10.0, 20.0]]],
        [[[10.0, 20.0], [12.0, 20.0], [12.0, 95.0], [10.0, 20.0]]],
        [[[10.0, 20.0], [12.0, 20.0], [True, 22.0], [10.0, 20.0]]],
        [[[10.0], [12.0], [14.0]]],
    ],
)
def test_malformed_geometry_is_rejected(value):
    with pytest.raises(geo.InvalidGeometry):
        geo.normalize_multipolygon(value)


def test_antimeridian_and_oversized_geometry_fail_closed():
    with pytest.raises(geo.InvalidGeometry):
        geo.normalize_multipolygon(
            [[[-179.0, 10.0], [179.0, 10.0], [179.0, 12.0], [-179.0, 10.0]]]
        )
    huge = [[float(i % 90), float(i % 45)] for i in range(geo.MAX_RING_POSITIONS + 2)]
    with pytest.raises(geo.InvalidGeometry):
        geo.normalize_multipolygon([huge])


# ---------------------------------------------------------------------------
# Containment
# ---------------------------------------------------------------------------


def test_point_clearly_inside_and_outside_a_polygon():
    assert inside(21.0, 11.0, SQUARE) is True
    assert inside(25.0, 11.0, SQUARE) is False
    assert inside(21.0, 30.0, SQUARE) is False


def test_point_inside_bounding_box_but_outside_polygon_does_not_match():
    # (1.5, 1.5) sits in the L's bounding box, in the missing quadrant.
    bounds = geo.multipolygon_bounds(geo.normalize_multipolygon(L_SHAPE))
    assert bounds.min_latitude <= 1.5 <= bounds.max_latitude
    assert bounds.longitude_ranges[0][0] <= 1.5 <= bounds.longitude_ranges[0][1]
    assert inside(1.5, 1.5, L_SHAPE) is False
    assert inside(0.5, 0.5, L_SHAPE) is True


@pytest.mark.parametrize(
    "latitude,longitude",
    [(20.0, 11.0), (22.0, 11.0), (21.0, 10.0), (21.0, 12.0), (20.0, 10.0), (22.0, 12.0)],
)
def test_points_exactly_on_the_boundary_match(latitude, longitude):
    """Documented rule: the boundary belongs to the warned area."""

    assert inside(latitude, longitude, SQUARE) is True


def test_ring_winding_direction_does_not_affect_matching():
    reversed_ring = [list(reversed(SQUARE[0]))]
    assert inside(21.0, 11.0, reversed_ring) is True
    assert inside(25.0, 11.0, reversed_ring) is False


def test_holes_are_excluded_but_their_boundary_matches():
    assert inside(21.0, 11.0, SQUARE_WITH_HOLE) is False
    assert inside(20.5, 10.5, SQUARE_WITH_HOLE) is True
    assert inside(20.8, 11.0, SQUARE_WITH_HOLE) is True


def test_multipolygon_matches_any_component_and_stays_disjoint():
    multi = [SQUARE, FAR_SQUARE]
    assert inside(21.0, 11.0, multi) is True
    assert inside(61.0, 51.0, multi) is True
    # Between the two components: no accidental merging.
    assert inside(40.0, 30.0, multi) is False
    assert len(geo.normalize_multipolygon(multi)) == 2


def test_bounds_cover_every_component():
    bounds = geo.multipolygon_bounds(geo.normalize_multipolygon([SQUARE, FAR_SQUARE]))
    assert (bounds.min_latitude, bounds.max_latitude) == (20.0, 62.0)
    assert bounds.longitude_ranges == ((10.0, 52.0),)


# ---------------------------------------------------------------------------
# Model storage and validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_hazard_event_stores_canonical_geometry_and_rejects_bad_geometry():
    hazard = HazardEvent(
        provider="usgs",
        provider_event_id="area-1",
        hazard_type="flood",
        title="Area hazard",
        latitude=Decimal("21.000000"),
        longitude=Decimal("11.000000"),
        occurred_at="2026-09-15T12:00:00Z",
        provider_updated_at="2026-09-15T12:00:00Z",
        last_seen_at="2026-09-15T12:00:00Z",
        area_polygons=SQUARE,
    )
    hazard.full_clean()
    assert hazard.area_polygons == [SQUARE]
    assert hazard.has_area_geometry is True

    hazard.area_polygons = [[[10.0, 20.0], [12.0, 20.0]]]
    with pytest.raises(ValidationError) as exc:
        hazard.full_clean()
    assert "area_polygons" in exc.value.message_dict


@pytest.mark.django_db
def test_hazard_event_without_area_geometry_is_unchanged():
    hazard = HazardEvent(
        provider="usgs",
        provider_event_id="point-1",
        hazard_type="earthquake",
        title="Point hazard",
        latitude=Decimal("30.044400"),
        longitude=Decimal("31.235700"),
        occurred_at="2026-09-15T12:00:00Z",
        provider_updated_at="2026-09-15T12:00:00Z",
        last_seen_at="2026-09-15T12:00:00Z",
    )
    hazard.full_clean()
    assert hazard.area_polygons is None
    assert hazard.has_area_geometry is False


# ---------------------------------------------------------------------------
# Project matching, including coexistence with point/radius
# ---------------------------------------------------------------------------


@pytest.fixture
def area_projects(db):
    admin = make_user(Role.SUPER_ADMIN, "geo-admin")
    return {
        "inside": make_project(
            admin, name="Inside square", latitude=Decimal("21.000000"), longitude=Decimal("11.000000")
        ),
        "in_hole": make_project(
            admin, name="In hole", latitude=Decimal("21.000000"), longitude=Decimal("11.000000")
        ),
        "outside": make_project(
            admin, name="Outside", latitude=Decimal("25.000000"), longitude=Decimal("11.000000")
        ),
        "far": make_project(
            admin, name="Far component", latitude=Decimal("61.000000"), longitude=Decimal("51.000000")
        ),
        "no_coords": make_project(admin, name="No coordinates", latitude=None, longitude=None),
    }


@pytest.mark.django_db
def test_match_projects_in_area_uses_exact_containment(area_projects):
    matches = geo.match_projects_in_area(Project.objects.all(), polygons=SQUARE)
    matched = {match.project.pk for match in matches}
    assert area_projects["inside"].pk in matched
    assert area_projects["outside"].pk not in matched
    assert area_projects["far"].pk not in matched
    assert area_projects["no_coords"].pk not in matched
    assert all(match.distance_km == Decimal("0.00") for match in matches)


@pytest.mark.django_db
def test_match_projects_in_area_excludes_holes_and_spans_components(area_projects):
    holed = {m.project.pk for m in geo.match_projects_in_area(Project.objects.all(), polygons=SQUARE_WITH_HOLE)}
    assert area_projects["inside"].pk not in holed

    multi = {
        m.project.pk
        for m in geo.match_projects_in_area(Project.objects.all(), polygons=[SQUARE, FAR_SQUARE])
    }
    assert {area_projects["inside"].pk, area_projects["far"].pk} <= multi
    assert area_projects["outside"].pk not in multi


@pytest.mark.django_db
def test_area_matching_rejects_malformed_geometry_without_matching(area_projects):
    with pytest.raises(geo.InvalidGeometry):
        geo.match_projects_in_area(Project.objects.all(), polygons=[[[10.0, 20.0], [12.0, 20.0]]])


@pytest.mark.django_db
def test_point_radius_and_area_matching_coexist(area_projects):
    """The original radius behaviour is untouched and independent."""

    radius_matches = geo.match_projects(
        Project.objects.all(), latitude=21.0, longitude=11.0, radius_km=50
    )
    radius_ids = {match.project.pk for match in radius_matches}
    assert area_projects["inside"].pk in radius_ids
    assert area_projects["far"].pk not in radius_ids
    assert area_projects["no_coords"].pk not in radius_ids
    # Radius matches still carry a real measured distance, not a sentinel.
    assert any(match.distance_km >= Decimal("0.00") for match in radius_matches)

    area_ids = {
        match.project.pk
        for match in geo.match_projects_in_area(Project.objects.all(), polygons=FAR_SQUARE)
    }
    assert area_ids == {area_projects["far"].pk}
    assert radius_ids & area_ids == set()
