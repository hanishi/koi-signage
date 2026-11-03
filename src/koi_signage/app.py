"""The venue as a web app: the guardian, the floor and screen WebSockets, and the pages.

    uv run uvicorn --factory koi_signage.app:from_env --host 0.0.0.0 --port 8124

Then open / on a laptop, or /screen?n=0..2 on each tablet."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi import Path as Param
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from ohra import ActorContext, ActorRef, ActorSystem, Behavior, Behaviors
from ohra.ext.fastapi import Actors
from pydantic import BaseModel, Field

from koi_signage.character import CharacterMsg, character
from koi_signage.display import decode_screen, display
from koi_signage.floor import decode_floor, floor
from koi_signage.messages import Ad
from koi_signage.venue import DEFAULT_VENUE, Venue, load_venue

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


class AdRequest(BaseModel):
    clip: str  # a file in the venue's ads dir
    # the slot, 15 s as is usual for signage: the clip holds its last frame or is cut to fit
    seconds: float = Field(default=15, gt=0)


def create_app(venue: Venue) -> FastAPI:
    actors = Actors(guardian(lambda: character(venue)), "koi-signage")
    app = FastAPI(
        title="koi-signage", lifespan=actors.lifespan, exception_handlers=actors.exception_handlers
    )
    app.mount("/static", StaticFiles(directory=STATIC), name="static")  # read per request
    app.mount("/ads", StaticFiles(directory=venue.ads_dir), name="ads")

    def clips() -> list[str]:  # read per request: drop a clip in and it can play
        files = venue.ads_dir.iterdir()
        return sorted(f.name for f in files if f.is_file() and not f.name.startswith("."))

    async def the_character(system: ActorSystem[GuardianMsg]) -> ActorRef[CharacterMsg]:
        return await system.ask(GetCharacter, timeout=2)

    @app.get("/")
    async def home() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/screen")
    async def screen() -> FileResponse:
        return FileResponse(STATIC / "screen.html")

    @app.get("/venue")
    async def floor_plan() -> dict[str, Any]:
        """What the page needs to draw the floor."""
        return {
            "screens": venue.screens,
            "width_m": venue.width_m,
            "depth_m": venue.depth_m,
            "zone_cuts_m": list(venue.zone_cuts_m),
            "radar": {
                "x_m": venue.radar_x_m,
                "range_m": venue.radar_range_m,
                "fov_deg": venue.radar_fov_deg,
            },
            "creative": venue.creative,
            "ads": clips(),
        }

    @app.post("/ads", status_code=202)
    async def play_ad(
        ad: AdRequest, system: ActorSystem[GuardianMsg] = actors.depends()
    ) -> dict[str, str]:
        """Interrupt the character: every screen plays ``clip`` for ``seconds``, then the
        character comes back. Promovolve's schedule will call this; the floor page does now."""
        if ad.clip not in clips():
            raise HTTPException(404, f"no clip {ad.clip!r} in {venue.ads_dir}")
        (await the_character(system)).tell(Ad(ad.clip, ad.seconds))
        return {"playing": ad.clip}

    @app.websocket("/ws/floor")
    async def floor_socket(
        ws: WebSocket, system: ActorSystem[GuardianMsg] = actors.depends()
    ) -> None:
        ch = await the_character(system)
        await actors.websocket(ws, lambda out: floor(venue, ch, out), decode_floor)

    @app.websocket("/ws/screen/{n}")
    async def screen_socket(
        ws: WebSocket,
        n: Annotated[int, Param(ge=0, le=venue.screens - 1)],
        system: ActorSystem[GuardianMsg] = actors.depends(),
    ) -> None:
        ch = await the_character(system)
        await actors.websocket(ws, lambda out: display(n, ch, out), decode_screen)

    return app


def from_env() -> FastAPI:
    """The app uvicorn starts (``--factory``), on ``$VENUE`` if set, else ``./venue.toml`` if
    there is one, else the defaults the package ships."""
    here = Path("venue.toml")
    path = os.environ.get("VENUE") or (here if here.exists() else DEFAULT_VENUE)
    return create_app(load_venue(Path(path)))
