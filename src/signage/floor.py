"""The floor page's connection actor: the mouse pointer as the radar.

The page sends where people are whenever that changes. This actor keeps the latest set and sends
Character a Frame every 100 ms, moving or not, as the LD2450 does. The LD2450 actor replaces this
one and sends the same Frame."""

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from ohra import ActorContext, ActorRef, Behavior, Behaviors

from signage.character import CharacterMsg
from signage.messages import AttachFloor, Frame, Status, Target
from signage.venue import Venue

MAX_TARGETS = 3  # the LD2450 tracks at most 3 people
FRAME_INTERVAL_S = 0.1  # the LD2450 reports at about 10 fps


@dataclass(frozen=True)
class Pointer:
    """Where the page says people are: the pointer, and anyone clicked onto the floor."""

    targets: tuple[Target, ...]


@dataclass(frozen=True)
class _Tick:
    pass


@dataclass(frozen=True)
class _CharacterGone:
    pass


type FloorMsg = Pointer | Status | _Tick | _CharacterGone


def _number(v: object) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        raise ValueError(f"not a finite number: {v!r}")
    return float(v)


def decode_floor(text: str) -> Pointer:
    """``{"targets": [{"x": n, "y": n}, ...]}``. Anything else raises ValueError, which closes the
    socket with 1003."""
    doc: object = json.loads(text)
    if not isinstance(doc, dict):
        raise ValueError("expected an object")
    targets = cast(dict[str, object], doc).get("targets")
    if not isinstance(targets, list):
        raise ValueError("expected a list of targets")
    out: list[Target] = []
    for t in cast(list[object], targets):
        if not isinstance(t, dict):
            raise ValueError("expected a target object")
        point = cast(dict[str, object], t)
        out.append(Target(_number(point.get("x")), _number(point.get("y"))))
    return Pointer(tuple(out))


def clamp(v: Venue, targets: Sequence[Target]) -> tuple[Target, ...]:
    """Drop points off the floor, then keep the first 3, as the radar would."""
    on = [t for t in targets if 0 <= t.x <= v.width_m and 0 <= t.y <= v.depth_m]
    return tuple(on[:MAX_TARGETS])


def floor(
    venue: Venue, character: ActorRef[CharacterMsg], out: ActorRef[dict[str, Any]]
) -> Behavior[FloorMsg]:
    def setup(ctx: ActorContext[FloorMsg]) -> Behavior[FloorMsg]:
        character.tell(AttachFloor(ctx.self))
        ctx.watch_with(character, _CharacterGone())  # a new character means a fresh page
        ctx.timers.start_timer_with_fixed_delay("tick", _Tick(), FRAME_INTERVAL_S)

        def run(latest: tuple[Target, ...]) -> Behavior[FloorMsg]:
            def on_message(_ctx: ActorContext[FloorMsg], msg: FloorMsg) -> Behavior[FloorMsg]:
                match msg:
                    case Pointer(targets):
                        return run(clamp(venue, targets))
                    case _Tick():
                        character.tell(Frame(latest))
                        return Behaviors.same
                    case Status(mode, count, screen):
                        out.tell(
                            {"type": "status", "mode": mode, "count": count, "screen": screen}
                        )
                        return Behaviors.same
                    case _CharacterGone():
                        return Behaviors.stopped()

            return Behaviors.receive(on_message)

        return run(())

    return Behaviors.setup(setup)
