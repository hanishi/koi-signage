"""One screen's connection actor: it lives exactly as long as its tablet's socket.

It passes Character's commands to the tablet as JSON, the tablet's ready back as Ready(n), and
answers the tablet's clock pings, so the tablet can run enter and exit at the venue's ``t``."""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from ohra import ActorContext, ActorRef, Behavior, Behaviors

from koi_signage.character import CharacterMsg
from koi_signage.floor import finite_number
from koi_signage.messages import (
    AttachScreen,
    Cancel,
    Enter,
    Exit,
    Idle,
    PlayAd,
    Prepare,
    Ready,
    ScreenCmd,
)


@dataclass(frozen=True)
class PageReady:
    pass


@dataclass(frozen=True)
class Ping:
    c: float  # the page's clock when it sent this


@dataclass(frozen=True)
class _CharacterGone:
    pass


type DisplayMsg = ScreenCmd | PageReady | Ping | _CharacterGone


def decode_screen(text: str) -> PageReady | Ping:
    """``{"type": "ready"}`` or ``{"type": "ping", "c": n}``. Anything else raises ValueError,
    which closes the socket with 1003."""
    doc: object = json.loads(text)
    if not isinstance(doc, dict):
        raise ValueError("expected an object")
    frame = cast(dict[str, object], doc)
    match frame.get("type"):
        case "ready":
            return PageReady()
        case "ping":
            return Ping(finite_number(frame.get("c")))
        case other:
            raise ValueError(f"unknown frame type: {other!r}")


def _json(cmd: ScreenCmd) -> dict[str, Any]:
    match cmd:
        case Idle():
            return {"type": "idle"}
        case Prepare():
            return {"type": "prepare"}
        case Cancel():
            return {"type": "cancel"}
        case Enter(t, side):
            return {"type": "enter", "t": t, "side": side}
        case Exit(t, side):
            return {"type": "exit", "t": t, "side": side}
        case PlayAd(clip, t):
            return {"type": "ad", "clip": clip, "t": t}


def display(
    n: int,
    character: ActorRef[CharacterMsg],
    out: ActorRef[dict[str, Any]],
    clock: Callable[[], float] = time.monotonic,
) -> Behavior[DisplayMsg]:
    """``clock`` must be the one Character stamps Enter and Exit with."""

    def setup(ctx: ActorContext[DisplayMsg]) -> Behavior[DisplayMsg]:
        character.tell(AttachScreen(n, ctx.self))
        ctx.watch_with(character, _CharacterGone())  # a new character means a fresh page

        def run(held: tuple[ScreenCmd, ...] | None) -> Behavior[DisplayMsg]:
            """``held``: commands kept until the page's first ping, None once it has one. Before
            that the page has no offset, so a ``t`` would land days away on its clock."""

            def on_message(
                _ctx: ActorContext[DisplayMsg], msg: DisplayMsg
            ) -> Behavior[DisplayMsg]:
                match msg:
                    case PageReady():
                        character.tell(Ready(n))
                    case Ping(c):
                        out.tell({"type": "pong", "c": c, "s": clock()})
                        if held is not None:
                            for cmd in held:
                                out.tell(_json(cmd))
                            return run(None)
                    case _CharacterGone():
                        return Behaviors.stopped()
                    case _:
                        if held is not None:
                            return run((*held, msg))
                        out.tell(_json(msg))
                return Behaviors.same

            return Behaviors.receive(on_message)

        return run(())

    return Behaviors.setup(setup)
