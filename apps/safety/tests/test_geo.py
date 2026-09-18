import math
from decimal import Decimal

import pytest

from apps.projects.models import Project
from apps.safety import geo
from apps.safety.tests.helpers import make_project


ONE_DEGREE_KM = 2 * math.pi * geo.EARTH_RADIUS_KM / 360


def test_haversine_zero_and_one_degree_along_meridian_and_equator():
    assert geo.haversine_km(10, 20, 10, 20) == 0
    assert geo.haversine_km(0, 0, 1, 0) == pytest.approx(ONE_DEGREE_KM, abs=1e-6)
    assert geo.haversine_km(0, 0, 0, 1) == pytest.approx(ONE_DEGREE_KM, abs=1e-6)


def test_haversine_antipodal_points_and_known_city_pair():
    assert geo.haversine_km(0, 0, 0, 180) == pytest.approx(math.pi * geo.EARTH_RADIUS_KM)
    london_paris = geo.haversine_km(51.5074, -0.1278, 48.8566, 2.3522)
    assert london_paris == pytest.approx(343.5, rel=0.005)


def test_haversine_accepts_decimals_and_is_symmetric():
    forward = geo.haversine_km(Decimal("30.0444"), Decimal("31.2357"), Decimal("31.2001"), Decimal("29.9187"))
    backward = geo.haversine_km(Decimal("31.2001"), Decimal("29.9187"), Decimal("30.0444"), Decimal("31.2357"))
    assert forward == pytest.approx(backward)


@pytest.mark.parametrize(
    "lat1,lon1",
    [(91, 0), (-90.5, 0), (0, 180.1), (None, 0), (float("nan"), 0), (True, 0), ("north", 0)],
)
def test_haversine_rejects_invalid_coordinates(lat1, lon1):
    with pytest.raises(geo.InvalidCoordinates):
        geo.haversine_km(lat1, lon1, 0, 0)


def test_bounding_box_normal_case_contains_center():
    box = geo.bounding_box(30, 31, 50)
    assert box.min_latitude < 30 < box.max_latitude
    assert len(box.longitude_ranges) == 1
    min_lon, max_lon = box.longitude_ranges[0]
    assert min_lon < 31 < max_lon


def test_bounding_box_splits_across_the_antimeridian_both_directions():
    east = geo.bounding_box(0, 179.9, 50)
    assert len(east.longitude_ranges) == 2
    assert east.longitude_ranges[0][1] == 180.0
    assert east.longitude_ranges[1][0] == -180.0
    assert east.longitude_ranges[1][1] < -179.0

    west = geo.bounding_box(0, -179.9, 50)
    assert len(west.longitude_ranges) == 2
    assert west.longitude_ranges[0][0] > 179.0


def test_bounding_box_near_pole_uses_every_longitude():
    box = geo.bounding_box(89.9, 10, 50)
    assert box.max_latitude == 90.0
    assert box.longitude_ranges == ((-180.0, 180.0),)
    south = geo.bounding_box(-89.95, 10, 20)
    assert south.min_latitude == -90.0
    assert south.longitude_ranges == ((-180.0, 180.0),)


@pytest.mark.parametrize("radius", [-1, float("inf"), None, geo.MAX_MATCH_RADIUS_KM + 1])
def test_bounding_box_rejects_invalid_radius(radius):
    with pytest.raises(geo.InvalidCoordinates):
        geo.bounding_box(0, 0, radius)


@pytest.mark.django_db
def test_match_projects_orders_by_distance_and_skips_missing_or_far(super_admin_user):
    near = make_project(super_admin_user, name="Near", latitude=Decimal("30.10"), longitude=Decimal("31.24"))
    nearer = make_project(super_admin_user, name="Nearer", latitude=Decimal("30.05"), longitude=Decimal("31.24"))
    make_project(super_admin_user, name="Far", latitude=Decimal("25.00"), longitude=Decimal("31.24"))
    make_project(super_admin_user, name="No coordinates", latitude=None, longitude=None)

    matches = geo.match_projects(
        Project.objects.all(),
        latitude=Decimal("30.0444"),
        longitude=Decimal("31.2357"),
        radius_km=20,
    )

    assert [match.project.pk for match in matches] == [nearer.pk, near.pk]
    assert all(isinstance(match.distance_km, Decimal) for match in matches)
    assert matches[0].distance_km < matches[1].distance_km


@pytest.mark.django_db
def test_match_projects_across_antimeridian(super_admin_user):
    east = make_project(super_admin_user, name="East", latitude=Decimal("-17.0"), longitude=Decimal("179.95"))
    west = make_project(super_admin_user, name="West", latitude=Decimal("-17.0"), longitude=Decimal("-179.95"))

    matches = geo.match_projects(
        Project.objects.all(),
        latitude=Decimal("-17.0"),
        longitude=Decimal("179.99"),
        radius_km=20,
    )

    assert {match.project.pk for match in matches} == {east.pk, west.pk}


@pytest.mark.django_db
def test_match_projects_includes_exact_radius_boundary(super_admin_user):
    project = make_project(super_admin_user, latitude=Decimal("30.500000"), longitude=Decimal("31.000000"))
    distance = geo.haversine_km(30, 31, project.latitude, project.longitude)

    inside = geo.match_projects(Project.objects.all(), latitude=30, longitude=31, radius_km=distance)
    outside = geo.match_projects(Project.objects.all(), latitude=30, longitude=31, radius_km=distance - 0.01)

    assert [match.project.pk for match in inside] == [project.pk]
    assert outside == []
