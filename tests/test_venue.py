from pathlib import Path

import pytest

from koi_signage.venue import (
    DEFAULT_VENUE,
    Target,
    boundaries,
    load_venue,
    screen_counts,
    screen_of,
    zone_of,
)

V = load_venue(DEFAULT_VENUE)


def test_loads_repo_venue() -> None:
    assert V.zone_cuts_m == (1, 2, 3, 4, 5, 6, 7, 8)
    assert V.ready_timeout_s == 1.0
    assert V.max_distance_m == 3.0
    assert V.screens == 3
    assert (V.radar_x_m, V.radar_range_m, V.radar_fov_deg) == (4.5, 6.0, 120.0)


def test_zone_and_screen_at_cuts() -> None:
    assert [zone_of(V, x) for x in (0.0, 0.99, 1.0, 8.0, 9.0)] == [0, 0, 1, 8, 8]
    assert [screen_of(V, x) for x in (2.99, 3.0, 5.99, 6.0)] == [0, 1, 1, 2]
    assert boundaries(V) == (3, 6)


def test_screen_counts() -> None:
    assert screen_counts(V, [Target(0.5, 1), Target(4, 1), Target(4.5, 2)]) == (1, 2, 0)


GOOD = DEFAULT_VENUE.read_text()


@pytest.mark.parametrize(
    "cuts",
    [
        "[1, 3, 2, 4, 5, 6, 7, 8]",  # not increasing
        "[1, 2, 3, 4, 5, 6, 7]",  # 7 cuts, not 8
        "[0, 2, 3, 4, 5, 6, 7, 8]",  # a cut on the floor's edge
        "[1, 2, 3, 4, 5, 6, 7, 9]",  # a cut at the far edge
    ],
)
def test_rejects_bad_cuts(tmp_path: Path, cuts: str) -> None:
    bad = tmp_path / "venue.toml"
    bad.write_text(GOOD.replace("[1, 2, 3, 4, 5, 6, 7, 8]", cuts))
    with pytest.raises(ValueError):
        load_venue(bad)


@pytest.mark.parametrize("m", ["0", "4.5"])
def test_rejects_max_distance_off_the_floor(tmp_path: Path, m: str) -> None:
    bad = tmp_path / "venue.toml"
    bad.write_text(GOOD.replace("max_distance_m = 3.0", f"max_distance_m = {m}"))
    with pytest.raises(ValueError):
        load_venue(bad)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("range_m = 6.0", "x_m = 9.5\nrange_m = 6.0"),  # off the screen line
        ("range_m = 6.0", "range_m = 0"),
        ("fov_deg = 120.0", "fov_deg = 181"),
        ("fov_deg = 120.0", "fov_deg = 0"),
    ],
)
def test_rejects_bad_radar(tmp_path: Path, old: str, new: str) -> None:
    bad = tmp_path / "venue.toml"
    bad.write_text(GOOD.replace(old, new))
    with pytest.raises(ValueError):
        load_venue(bad)


FOUR = (
    GOOD.replace("screens = 3", "screens = 4")
    .replace("width_m = 9.0", "width_m = 12.0")
    .replace("[1, 2, 3, 4, 5, 6, 7, 8]", "[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]")
)


def test_four_screens(tmp_path: Path) -> None:
    four = tmp_path / "venue.toml"
    four.write_text(FOUR)
    v = load_venue(four)
    assert v.screens == 4
    assert boundaries(v) == (3, 6, 9)
    assert [screen_of(v, x) for x in (2.9, 3.0, 9.0, 11.9)] == [0, 1, 3, 3]
    assert screen_counts(v, [Target(1, 1), Target(10, 1), Target(11, 2)]) == (1, 0, 0, 2)


@pytest.mark.parametrize(
    "screens",
    [
        "4",  # 4 screens need 11 cuts, and there are 8
        "0",
        "2.5",
    ],
)
def test_rejects_bad_screen_count(tmp_path: Path, screens: str) -> None:
    bad = tmp_path / "venue.toml"
    bad.write_text(GOOD.replace("screens = 3", f"screens = {screens}"))
    with pytest.raises(ValueError):
        load_venue(bad)


def test_radar_centred_on_the_floor_unless_placed(tmp_path: Path) -> None:
    four = tmp_path / "venue.toml"
    four.write_text(FOUR)
    assert load_venue(four).radar_x_m == 6.0  # the middle of 12 m, without being told
    four.write_text(FOUR.replace("range_m = 6.0", "x_m = 2.0\nrange_m = 6.0"))
    assert load_venue(four).radar_x_m == 2.0
