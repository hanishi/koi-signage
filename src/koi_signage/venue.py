"""One venue's calibration, and tracking: where people are, as zones and screens.

Tracking is pure functions while it holds no state. It becomes an actor when smoothing or
standing-person memory needs some."""

import math
import tomllib
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ZONES_PER_SCREEN = 3
SCREENS = 3
DEFAULT_VENUE = Path(__file__).with_name("venue.toml")  # the defaults the package ships


@dataclass(frozen=True)
class Target:
    """One person on the floor, in metres: x along the corridor, y away from the screens."""

    x: float
    y: float


@dataclass(frozen=True)
class Venue:
    width_m: float
    depth_m: float
    zone_cuts_m: tuple[float, ...]
    max_distance_m: float
    radar_x_m: float
    radar_range_m: float
    radar_fov_deg: float
    follow_after_s: float
    crowd_after_s: float
    idle_after_s: float
    crowd_lead_s: float
    linger_s: float
    dead_zone_m: float
    handoff_lead_s: float
    ready_timeout_s: float


def load_venue(path: Path) -> Venue:
    """Read ``venue.toml``. Raises ValueError unless there are 8 strictly increasing zone cuts,
    all inside the floor, max_distance_m is in (0, depth_m], and the radar is on the screen line
    with a positive range and a field of view in (0, 180]."""
    with path.open("rb") as f:
        doc = tomllib.load(f)
    floor, ch, radar = doc["floor"], doc["character"], doc["radar"]
    width = float(floor["width_m"])
    cuts = tuple(float(c) for c in floor["zone_cuts_m"])
    if len(cuts) != ZONES_PER_SCREEN * SCREENS - 1:
        raise ValueError(f"zone_cuts_m needs {ZONES_PER_SCREEN * SCREENS - 1} cuts")
    if any(a >= b for a, b in zip((0.0, *cuts), (*cuts, width))):
        raise ValueError("zone_cuts_m must increase strictly, inside (0, width_m)")
    depth, reach = float(floor["depth_m"]), float(floor["max_distance_m"])
    if not 0 < reach <= depth:
        raise ValueError("max_distance_m must be in (0, depth_m]")
    rx, rr, fov = float(radar["x_m"]), float(radar["range_m"]), float(radar["fov_deg"])
    if not (0 <= rx <= width and rr > 0 and 0 < fov <= 180):
        raise ValueError("radar needs x_m in [0, width_m], range_m > 0, fov_deg in (0, 180]")
    return Venue(
        width_m=width,
        depth_m=depth,
        zone_cuts_m=cuts,
        max_distance_m=reach,
        radar_x_m=rx,
        radar_range_m=rr,
        radar_fov_deg=fov,
        follow_after_s=float(ch["follow_after_s"]),
        crowd_after_s=float(ch["crowd_after_s"]),
        idle_after_s=float(ch["idle_after_s"]),
        crowd_lead_s=float(ch["crowd_lead_s"]),
        linger_s=float(ch["linger_s"]),
        dead_zone_m=float(ch["dead_zone_m"]),
        handoff_lead_s=float(ch["handoff_lead_s"]),
        ready_timeout_s=float(ch["ready_timeout_s"]),
    )


def in_view(v: Venue, t: Target) -> bool:
    """Whether the radar can see ``t``: within its range, and within half its field of view of
    straight out from the screens."""
    dx = t.x - v.radar_x_m
    angle = math.degrees(math.atan2(abs(dx), t.y))
    return math.hypot(dx, t.y) <= v.radar_range_m and angle <= v.radar_fov_deg / 2


def zone_of(v: Venue, x: float) -> int:
    """0..8. A point on a cut belongs to the zone on its right."""
    return bisect_right(v.zone_cuts_m, x)


def screen_of(v: Venue, x: float) -> int:
    return zone_of(v, x) // ZONES_PER_SCREEN


def boundaries(v: Venue) -> tuple[float, float]:
    """The x of the boundary between screens 0 and 1, and between 1 and 2."""
    return v.zone_cuts_m[ZONES_PER_SCREEN - 1], v.zone_cuts_m[2 * ZONES_PER_SCREEN - 1]


def screen_counts(v: Venue, targets: Sequence[Target]) -> tuple[int, int, int]:
    counts = [0] * SCREENS
    for t in targets:
        counts[screen_of(v, t.x)] += 1
    return counts[0], counts[1], counts[2]
