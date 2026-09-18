"""Geospatial helpers for matching hazards to project coordinates.

No PostGIS: candidates are narrowed with a latitude/longitude bounding box in
SQL, then confirmed with an exact haversine distance in Python. Projects
without coordinates are never matched and never treated as (0, 0).
"""

import math
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from django.db.models import Q


EARTH_RADIUS_KM = 6371.0088
MAX_MATCH_RADIUS_KM = 2000.0
_COORDINATE_QUANTUM = Decimal("0.000001")
_DISTANCE_QUANTUM = Decimal("0.01")


class InvalidCoordinates(ValueError):
    """A coordinate or radius is missing, non-finite, or out of range."""


@dataclass(frozen=True)
class BoundingBox:
    min_latitude: float
    max_latitude: float
    # One range normally; two when the box crosses the antimeridian.
    longitude_ranges: tuple


@dataclass(frozen=True)
class ProjectMatch:
    project: object
    distance_km: Decimal


def _coordinate(value, *, limit, name):
    if value is None or isinstance(value, bool):
        raise InvalidCoordinates(f"{name} is required.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidCoordinates(f"{name} must be numeric.") from exc
    if not math.isfinite(number) or number < -limit or number > limit:
        raise InvalidCoordinates(f"{name} is out of range.")
    return number


def _latitude(value):
    return _coordinate(value, limit=90.0, name="latitude")


def _longitude(value):
    return _coordinate(value, limit=180.0, name="longitude")


def _radius(value):
    if value is None or isinstance(value, bool):
        raise InvalidCoordinates("radius_km is required.")
    try:
        radius = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidCoordinates("radius_km must be numeric.") from exc
    if not math.isfinite(radius) or radius < 0 or radius > MAX_MATCH_RADIUS_KM:
        raise InvalidCoordinates("radius_km is out of range.")
    return radius


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in kilometres between two coordinate pairs."""

    phi1 = math.radians(_latitude(lat1))
    phi2 = math.radians(_latitude(lat2))
    delta_phi = phi2 - phi1
    delta_lambda = math.radians(_longitude(lon2) - _longitude(lon1))
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    a = min(1.0, max(0.0, a))
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def quantize_distance(distance_km):
    return Decimal(str(distance_km)).quantize(_DISTANCE_QUANTUM, rounding=ROUND_HALF_UP)


def bounding_box(latitude, longitude, radius_km):
    """Return a box that contains every point within ``radius_km``.

    The box is conservative (it may include a few points slightly outside the
    radius); the haversine check makes the final decision.
    """

    lat = _latitude(latitude)
    lon = _longitude(longitude)
    radius = _radius(radius_km)
    angular = radius / EARTH_RADIUS_KM
    delta_lat = math.degrees(angular)
    min_lat = lat - delta_lat
    max_lat = lat + delta_lat

    if min_lat <= -90.0 or max_lat >= 90.0:
        # The circle reaches a pole, so every longitude is a candidate.
        return BoundingBox(max(min_lat, -90.0), min(max_lat, 90.0), ((-180.0, 180.0),))

    sin_ratio = math.sin(angular) / math.cos(math.radians(lat))
    if sin_ratio >= 1.0:
        return BoundingBox(min_lat, max_lat, ((-180.0, 180.0),))
    delta_lon = math.degrees(math.asin(sin_ratio))
    min_lon = lon - delta_lon
    max_lon = lon + delta_lon
    if delta_lon >= 180.0:
        ranges = ((-180.0, 180.0),)
    elif min_lon < -180.0:
        ranges = ((min_lon + 360.0, 180.0), (-180.0, max_lon))
    elif max_lon > 180.0:
        ranges = ((min_lon, 180.0), (-180.0, max_lon - 360.0))
    else:
        ranges = ((min_lon, max_lon),)
    return BoundingBox(min_lat, max_lat, ranges)


def _floor(value):
    return Decimal(repr(value)).quantize(_COORDINATE_QUANTUM, rounding=ROUND_FLOOR)


def _ceil(value):
    return Decimal(repr(value)).quantize(_COORDINATE_QUANTUM, rounding=ROUND_CEILING)


def bounding_box_q(box, *, latitude_field="latitude", longitude_field="longitude"):
    """Translate a BoundingBox into a Django ``Q`` prefilter."""

    longitude_q = Q()
    for min_lon, max_lon in box.longitude_ranges:
        longitude_q |= Q(
            **{
                f"{longitude_field}__gte": _floor(min_lon),
                f"{longitude_field}__lte": _ceil(max_lon),
            }
        )
    return (
        Q(**{f"{latitude_field}__isnull": False, f"{longitude_field}__isnull": False})
        & Q(
            **{
                f"{latitude_field}__gte": _floor(box.min_latitude),
                f"{latitude_field}__lte": _ceil(box.max_latitude),
            }
        )
        & longitude_q
    )


def match_projects(projects, *, latitude, longitude, radius_km):
    """Return projects within ``radius_km`` of a point, nearest first.

    ``projects`` is a Project queryset already narrowed to monitored projects.
    Rows without both coordinates are excluded by the prefilter.
    """

    box = bounding_box(latitude, longitude, radius_km)
    radius = _radius(radius_km)
    matches = []
    for project in projects.filter(bounding_box_q(box)).order_by("pk"):
        if project.latitude is None or project.longitude is None:
            continue
        distance = haversine_km(latitude, longitude, project.latitude, project.longitude)
        if distance <= radius:
            matches.append(ProjectMatch(project=project, distance_km=quantize_distance(distance)))
    matches.sort(key=lambda match: (match.distance_km, str(match.project.pk)))
    return matches


# ---------------------------------------------------------------------------
# Polygon / MultiPolygon area geometry
#
# An additional, optional geometry mode alongside the point+radius matching
# above, for providers that publish an authoritative warned *area* rather than
# a centre and a radius. The two modes never mix: a hazard carrying area
# geometry is matched by exact containment, and a hazard without it keeps the
# radius behaviour unchanged.
#
# Coordinate convention: positions are ``[longitude, latitude]``, the GeoJSON
# order (RFC 7946) — deliberately the opposite of the ``(latitude, longitude)``
# argument order used by the functions above. Every position is range-checked
# on the way in, which rejects most accidentally swapped pairs.
#
# No centroid, bounding circle, or bounding box ever decides a match. The
# bounding box is only a SQL prefilter; containment is always confirmed
# exactly in Python.
# ---------------------------------------------------------------------------

# Bounds keep one malformed or hostile provider response from pinning a worker.
MAX_AREA_POLYGONS = 64
MAX_AREA_RINGS = 128
MAX_RING_POSITIONS = 4000
MAX_AREA_POSITIONS = 20000
MIN_RING_POSITIONS = 3
# A polygon wider than half the globe is either antimeridian-crossing or
# degenerate. Neither is supported, so both fail closed (see README).
MAX_POLYGON_LONGITUDE_SPAN = 180.0
# Tolerance for "exactly on the boundary", in degrees (~0.1 mm).
BOUNDARY_EPSILON = 1e-9


class InvalidGeometry(ValueError):
    """Area geometry is missing, malformed, or unsupported.

    Deliberately not a subclass of :class:`InvalidCoordinates`, so existing
    point/radius error handling is unaffected.
    """


def _is_number(value):
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def _looks_like_position(value):
    return (
        isinstance(value, (list, tuple))
        and len(value) >= 2
        and _is_number(value[0])
        and _is_number(value[1])
    )


def _position(value):
    if not _looks_like_position(value):
        raise InvalidGeometry("A position must be a [longitude, latitude] pair of numbers.")
    longitude = float(value[0])
    latitude = float(value[1])
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        raise InvalidGeometry("Positions must be finite.")
    if not -180.0 <= longitude <= 180.0:
        raise InvalidGeometry("Longitude is out of range.")
    if not -90.0 <= latitude <= 90.0:
        raise InvalidGeometry("Latitude is out of range.")
    return [longitude, latitude]


def _ring(value, budget):
    if not isinstance(value, (list, tuple)) or not value:
        raise InvalidGeometry("A ring must be a non-empty list of positions.")
    if len(value) > MAX_RING_POSITIONS:
        raise InvalidGeometry("A ring has too many positions.")
    positions = [_position(item) for item in value]
    # Accept closed (GeoJSON) and unclosed rings; store the closed form.
    if positions[0] != positions[-1]:
        positions.append(list(positions[0]))
    distinct = {(x, y) for x, y in positions}
    if len(distinct) < MIN_RING_POSITIONS:
        raise InvalidGeometry("A ring needs at least three distinct positions.")
    budget["positions"] += len(positions)
    budget["rings"] += 1
    if budget["rings"] > MAX_AREA_RINGS:
        raise InvalidGeometry("The geometry has too many rings.")
    if budget["positions"] > MAX_AREA_POSITIONS:
        raise InvalidGeometry("The geometry has too many positions.")
    return positions


def _polygon(value, budget):
    if not isinstance(value, (list, tuple)) or not value:
        raise InvalidGeometry("A polygon must be a non-empty list of rings.")
    rings = [_ring(ring, budget) for ring in value]
    longitudes = [x for ring in rings for x, _ in ring]
    if max(longitudes) - min(longitudes) > MAX_POLYGON_LONGITUDE_SPAN:
        raise InvalidGeometry(
            "Antimeridian-crossing or degenerate polygons are not supported."
        )
    return rings


def normalize_multipolygon(value):
    """Validate area geometry and return it in canonical MultiPolygon form.

    Accepts GeoJSON ``Polygon`` coordinates (a list of rings) or
    ``MultiPolygon`` coordinates (a list of polygons) and always returns the
    MultiPolygon shape: ``[[[ [lon, lat], ... ], ...], ...]``. Raises
    :class:`InvalidGeometry` for anything it cannot represent exactly.
    """

    if not isinstance(value, (list, tuple)) or not value:
        raise InvalidGeometry("Area geometry must be a non-empty list.")
    try:
        first = value[0]
        if not isinstance(first, (list, tuple)) or not first:
            raise InvalidGeometry("Area geometry must contain rings or polygons.")
        single_polygon = _looks_like_position(first[0])
    except InvalidGeometry:
        raise
    except (TypeError, IndexError, KeyError) as exc:
        raise InvalidGeometry("Area geometry is malformed.") from exc

    budget = {"rings": 0, "positions": 0}
    polygons = [_polygon(value, budget)] if single_polygon else [
        _polygon(polygon, budget) for polygon in value
    ]
    if not polygons or len(polygons) > MAX_AREA_POLYGONS:
        raise InvalidGeometry("Unsupported number of polygons.")
    return polygons


def multipolygon_bounds(polygons):
    """Return the BoundingBox enclosing normalized MultiPolygon coordinates."""

    if not polygons:
        raise InvalidGeometry("Area geometry is empty.")
    latitudes = [y for polygon in polygons for ring in polygon for _, y in ring]
    longitudes = [x for polygon in polygons for ring in polygon for x, _ in ring]
    if not latitudes:
        raise InvalidGeometry("Area geometry is empty.")
    return BoundingBox(min(latitudes), max(latitudes), ((min(longitudes), max(longitudes)),))


def _on_ring_boundary(x, y, ring):
    for (ax, ay), (bx, by) in zip(ring, ring[1:]):
        cross = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
        if abs(cross) > BOUNDARY_EPSILON:
            continue
        if (
            min(ax, bx) - BOUNDARY_EPSILON <= x <= max(ax, bx) + BOUNDARY_EPSILON
            and min(ay, by) - BOUNDARY_EPSILON <= y <= max(ay, by) + BOUNDARY_EPSILON
        ):
            return True
    return False


def _strictly_inside_ring(x, y, ring):
    """Even-odd ray casting. Independent of ring winding direction."""

    inside = False
    for (ax, ay), (bx, by) in zip(ring, ring[1:]):
        if (ay > y) != (by > y):
            crossing_x = ax + (y - ay) * (bx - ax) / (by - ay)
            if x < crossing_x:
                inside = not inside
    return inside


def point_in_multipolygon(latitude, longitude, polygons):
    """True when a point lies within normalized MultiPolygon coordinates.

    A point inside any component polygon matches. Within a polygon, the first
    ring is the exterior and any further rings are holes: inside the exterior
    and outside every hole matches, inside a hole does not.

    Boundary rule: a point lying exactly on any ring — exterior or hole — is
    treated as inside the warned area. Warning is the safe direction for a
    point on the edge, and it matches the inclusive ``distance <= radius``
    rule used by point/radius matching.
    """

    y = _latitude(latitude)
    x = _longitude(longitude)
    for polygon in polygons:
        if not polygon:
            continue
        if any(_on_ring_boundary(x, y, ring) for ring in polygon):
            return True
        if not _strictly_inside_ring(x, y, polygon[0]):
            continue
        if any(_strictly_inside_ring(x, y, hole) for hole in polygon[1:]):
            continue
        return True
    return False


def match_projects_in_area(projects, *, polygons):
    """Return projects lying inside authoritative area geometry.

    The bounding box only narrows the SQL candidates; every candidate is then
    confirmed by exact containment, so a project inside the box but outside
    the polygon never matches. ``distance_km`` is ``0.00``: the project is
    within the warned area itself, not a measured distance from a centre.
    """

    area = normalize_multipolygon(polygons)
    box = multipolygon_bounds(area)
    matches = []
    for project in projects.filter(bounding_box_q(box)).order_by("pk"):
        if project.latitude is None or project.longitude is None:
            continue
        if point_in_multipolygon(project.latitude, project.longitude, area):
            matches.append(ProjectMatch(project=project, distance_km=Decimal("0.00")))
    matches.sort(key=lambda match: str(match.project.pk))
    return matches
