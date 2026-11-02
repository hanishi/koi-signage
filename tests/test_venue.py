from pathlib import Path

import pytest

from signage.venue import Target, boundaries, load_venue, screen_counts, screen_of, zone_of

V = load_venue(Path(__file__).parent.parent / "venue.toml")


def test_loads_repo_venue() -> None:
    assert V.zone_cuts_m == (1, 2, 3, 4, 5, 6, 7, 8)
    assert V.ready_timeout_s == 1.0
    assert V.max_distance_m == 3.0


def test_zone_and_screen_at_cuts() -> None:
    assert [zone_of(V, x) for x in (0.0, 0.99, 1.0, 8.0, 9.0)] == [0, 0, 1, 8, 8]
    assert [screen_of(V, x) for x in (2.99, 3.0, 5.99, 6.0)] == [0, 1, 1, 2]
    assert boundaries(V) == (3, 6)


def test_screen_counts() -> None:
    assert screen_counts(V, [Target(0.5, 1), Target(4, 1), Target(4.5, 2)]) == (1, 2, 0)


GOOD = Path(__file__).parent.parent.joinpath("venue.toml").read_text()


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
