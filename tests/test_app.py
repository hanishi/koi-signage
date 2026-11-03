"""The app over its WebSockets, and the guardian's respawn."""

import tomllib
from pathlib import Path
from typing import Any

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from ohra import ActorRef, Behavior, Behaviors
from ohra.testkit import ActorTestKit, TestProbe
from starlette.testclient import WebSocketTestSession

from koi_signage.app import GetCharacter, create_app, from_env, guardian
from koi_signage.character import CharacterMsg
from koi_signage.messages import Frame
from koi_signage.venue import DEFAULT_VENUE
from util import V, V4


def until(ws: WebSocketTestSession, kind: str, limit: int = 50) -> dict[str, Any]:
    """The first frame of type ``kind``, within ``limit`` frames."""
    for _ in range(limit):
        frame: dict[str, Any] = ws.receive_json()
        if frame["type"] == kind:
            return frame
    raise AssertionError(f"no {kind} frame within {limit}")


def synced(ws: WebSocketTestSession) -> None:
    """What screen.js does on open: a ping, answered by a pong before any command."""
    ws.send_json({"type": "ping", "c": 0.0})
    assert ws.receive_json()["type"] == "pong"


def test_screen_gets_idle_after_first_ping() -> None:
    with TestClient(create_app(V)) as client, client.websocket_connect("/ws/screen/0") as ws:
        synced(ws)
        assert ws.receive_json() == {"type": "idle"}


def test_floor_and_screen_follow() -> None:
    with TestClient(create_app(V)) as client:
        with client.websocket_connect("/ws/screen/1") as screen:
            synced(screen)
            assert screen.receive_json() == {"type": "idle"}
            with client.websocket_connect("/ws/floor") as floor:
                floor.send_json({"targets": [{"x": 4, "y": 1}]})
                assert until(screen, "enter")["t"] > 0  # after follow_after_s of real time
                status = until(floor, "status")
                while status["mode"] != "follow":
                    status = until(floor, "status")
                assert status == {"type": "status", "mode": "follow", "count": 1, "screen": 1}


def test_venue_for_the_page() -> None:
    with TestClient(create_app(V)) as client:
        assert client.get("/venue").json() == {
            "width_m": 9.0,
            "depth_m": 4.0,
            "screens": 3,
            "zone_cuts_m": [1, 2, 3, 4, 5, 6, 7, 8],
            "radar": {"x_m": 4.5, "range_m": 6.0, "fov_deg": 120.0},
            "creative": "koi",
        }


def test_pages_served() -> None:
    with TestClient(create_app(V)) as client:
        assert "connectScreen" in client.get("/").text
        assert "connectScreen" in client.get("/screen").text
        js = client.get("/static/screen.js")
        assert js.headers["content-type"].startswith("text/javascript")
        assert "export function create" in client.get("/static/creatives/koi.js").text
        assert client.get("/static/app.py").status_code == 404


def test_bad_screen_index_rejected() -> None:
    with TestClient(create_app(V)) as client:
        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/screen/3"):
            pass


def test_bad_floor_frame_closes_1003() -> None:
    with TestClient(create_app(V)) as client, client.websocket_connect("/ws/floor") as ws:
        ws.send_text("nope")
        with pytest.raises(WebSocketDisconnect) as closed:
            until(ws, "never")
    assert closed.value.code == 1003


def crashing() -> Behavior[CharacterMsg]:
    def on_message(_msg: CharacterMsg) -> Behavior[CharacterMsg]:
        raise RuntimeError("a bug in the character")

    return Behaviors.receive_message(on_message)


async def test_guardian_respawns_character() -> None:
    async with ActorTestKit() as testkit:
        ref = testkit.spawn(guardian(crashing))
        replies: TestProbe[ActorRef[CharacterMsg]] = testkit.create_test_probe()
        watcher: TestProbe[None] = testkit.create_test_probe()
        ref.tell(GetCharacter(replies.ref))
        first = await replies.receive_message()
        first.tell(Frame(()))  # it crashes, and stops
        await watcher.expect_terminated(first)
        ref.tell(GetCharacter(replies.ref))
        second = await replies.receive_message()
        assert second != first
        await watcher.expect_no_message(0.05)  # alive: not terminated


def depth_served() -> float:
    with TestClient(from_env()) as client:
        return client.get("/venue").json()["depth_m"]


def test_from_env_falls_back_to_the_packaged_venue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Installed from PyPI and run from an empty directory, it still starts."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VENUE", raising=False)
    assert depth_served() == V.depth_m


def test_from_env_prefers_venue_toml_here_then_dollar_venue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VENUE", raising=False)
    here = DEFAULT_VENUE.read_text().replace("depth_m = 4.0", "depth_m = 5.0")
    (tmp_path / "venue.toml").write_text(here)
    assert depth_served() == 5.0
    other = tmp_path / "other.toml"
    other.write_text(here.replace("depth_m = 5.0", "depth_m = 6.0"))
    monkeypatch.setenv("VENUE", str(other))
    assert depth_served() == 6.0


def test_screen_count_from_the_venue() -> None:
    with TestClient(create_app(V4)) as client:
        assert client.get("/venue").json()["screens"] == 4
        with client.websocket_connect("/ws/screen/3") as ws:
            ws.send_json({"type": "ping", "c": 0.0})
            assert ws.receive_json()["type"] == "pong"
        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/screen/4"):
            pass


def test_every_static_file_is_package_data() -> None:
    """A pip install has every page, creative, image and library the source tree has."""
    pkg = Path(__file__).parents[1] / "src" / "koi_signage"
    pyproject = tomllib.loads((pkg.parents[1] / "pyproject.toml").read_text())
    globs = pyproject["tool"]["setuptools"]["package-data"]["koi_signage"]
    shipped = {p for g in globs for p in pkg.glob(g) if p.is_file()}
    assert {p for p in (pkg / "static").rglob("*") if p.is_file()} - shipped == set()


def test_image_creative_served() -> None:
    with TestClient(create_app(V)) as client:
        png = client.get("/static/creatives/koi-pixi/0.png")
        assert png.headers["content-type"] == "image/png"
        # a module script must come as JavaScript, or the browser refuses to run it
        pixi = client.get("/static/vendor/pixi-8.22.0.min.mjs")
        assert pixi.headers["content-type"].startswith("text/javascript")
