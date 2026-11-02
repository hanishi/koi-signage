"""The app over its WebSockets, and the guardian's respawn."""

from typing import Any

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from ohra import ActorRef, Behavior, Behaviors
from ohra.testkit import ActorTestKit, TestProbe
from starlette.testclient import WebSocketTestSession

from signage.app import GetCharacter, create_app, guardian
from signage.character import CharacterMsg
from signage.messages import Frame
from util import V


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
            "zone_cuts_m": [1, 2, 3, 4, 5, 6, 7, 8],
        }


def test_pages_served() -> None:
    with TestClient(create_app(V)) as client:
        assert "connectScreen" in client.get("/").text
        assert "connectScreen" in client.get("/screen").text
        js = client.get("/static/screen.js")
        assert js.headers["content-type"].startswith("text/javascript")
        assert "export function pond" in client.get("/static/koi.js").text
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
