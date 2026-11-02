"""One screen's connection actor: it lives exactly as long as its tablet's socket.

It passes Character's commands to the tablet as JSON, the tablet's ready back as Ready(n), and
answers the tablet's clock pings, so the tablet can run enter and exit at the venue's ``t``."""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from ohra import ActorContext, ActorRef, Behavior, Behaviors

from signage.character import CharacterMsg
from signage.floor import finite_number
from signage.messages import AttachScreen, Cancel, Enter, Exit, Idle, Prepare, Ready, ScreenCmd


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
        case Enter(t):
            return {"type": "enter", "t": t}
        case Exit(t):
            return {"type": "exit", "t": t}


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

        def on_message(_ctx: ActorContext[DisplayMsg], msg: DisplayMsg) -> Behavior[DisplayMsg]:
            match msg:
                case PageReady():
                    character.tell(Ready(n))
                case Ping(c):
                    out.tell({"type": "pong", "c": c, "s": clock()})
                case _CharacterGone():
                    return Behaviors.stopped()
                case _:
                    out.tell(_json(msg))
            return Behaviors.same

        return Behaviors.receive(on_message)

    return Behaviors.setup(setup)
