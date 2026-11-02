"""The venue as a web app: the guardian, the floor and screen WebSockets, and the pages.

    uv run uvicorn --factory signage.app:from_env --host 0.0.0.0 --port 8124

Then open / on a laptop, or /screen?n=0..2 on each tablet."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, WebSocket
from fastapi import Path as Param
from fastapi.responses import HTMLResponse, Response
from ohra import ActorContext, ActorRef, ActorSystem, Behavior, Behaviors
from ohra.ext.fastapi import Actors

from signage.character import CharacterMsg, character
from signage.display import decode_screen, display
from signage.floor import decode_floor, floor
from signage.venue import SCREENS, Venue, load_venue

STATIC = Path(__file__).parent / "static"


@dataclass(frozen=True)
class GetCharacter:
    reply_to: ActorRef[ActorRef[CharacterMsg]]


@dataclass(frozen=True)
class _CharacterStopped:
    ref: ActorRef[CharacterMsg]


type GuardianMsg = GetCharacter | _CharacterStopped


def guardian(make_character: Callable[[], Behavior[CharacterMsg]]) -> Behavior[GuardianMsg]:
    """Spawns the character and hands it to each connection. A character that stopped (a bug:
    it isn't restarted, because a restarted one keeps its ref, so no page would reconnect and
    it would have no screens) is replaced by a fresh one for the next connection. Its
    connection actors watch it, so their pages reconnect and get the fresh one."""

    def setup(ctx: ActorContext[GuardianMsg]) -> Behavior[GuardianMsg]:
        def spawn(k: int) -> ActorRef[CharacterMsg]:
            ref = ctx.spawn(make_character(), f"character-{k}")
            ctx.watch_with(ref, _CharacterStopped(ref))
            return ref

        def run(k: int, current: ActorRef[CharacterMsg] | None) -> Behavior[GuardianMsg]:
            def on_message(
                _ctx: ActorContext[GuardianMsg], msg: GuardianMsg
            ) -> Behavior[GuardianMsg]:
                match msg:
                    case GetCharacter(reply_to):
                        if current is not None:
                            reply_to.tell(current)
                            return Behaviors.same
                        fresh = spawn(k + 1)
                        reply_to.tell(fresh)
                        return run(k + 1, fresh)
                    case _CharacterStopped(ref):
                        return run(k, None) if ref == current else Behaviors.same

            return Behaviors.receive(on_message)

        return run(0, spawn(0))

    return Behaviors.setup(setup)


def create_app(venue: Venue) -> FastAPI:
    actors = Actors(guardian(lambda: character(venue)), "signage")
    app = FastAPI(
        title="signage", lifespan=actors.lifespan, exception_handlers=actors.exception_handlers
    )
    index = (STATIC / "index.html").read_text()
    screen_page = (STATIC / "screen.html").read_text()
    screen_js = (STATIC / "screen.js").read_text()

    async def the_character(system: ActorSystem[GuardianMsg]) -> ActorRef[CharacterMsg]:
        return await system.ask(GetCharacter, timeout=2)

    @app.get("/")
    async def home() -> HTMLResponse:
        return HTMLResponse(index)

    @app.get("/screen")
    async def screen() -> HTMLResponse:
        return HTMLResponse(screen_page)

    @app.get("/static/screen.js")
    async def script() -> Response:
        return Response(screen_js, media_type="text/javascript")

    @app.get("/venue")
    async def floor_plan() -> dict[str, Any]:
        """What the page needs to draw the floor."""
        return {
            "width_m": venue.width_m,
            "depth_m": venue.depth_m,
            "zone_cuts_m": list(venue.zone_cuts_m),
        }

    @app.websocket("/ws/floor")
    async def floor_socket(
        ws: WebSocket, system: ActorSystem[GuardianMsg] = actors.depends()
    ) -> None:
        ch = await the_character(system)
        await actors.websocket(ws, lambda out: floor(venue, ch, out), decode_floor)

    @app.websocket("/ws/screen/{n}")
    async def screen_socket(
        ws: WebSocket,
        n: Annotated[int, Param(ge=0, le=SCREENS - 1)],
        system: ActorSystem[GuardianMsg] = actors.depends(),
    ) -> None:
        ch = await the_character(system)
        await actors.websocket(ws, lambda out: display(n, ch, out), decode_screen)

    return app


def from_env() -> FastAPI:
    """The app uvicorn starts (``--factory``), on ``$VENUE`` (default ``venue.toml``)."""
    return create_app(load_venue(Path(os.environ.get("VENUE", "venue.toml"))))
