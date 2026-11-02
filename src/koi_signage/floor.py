"""The floor page's connection actor: the mouse pointer as the radar.

The page sends where people are whenever that changes. This actor keeps the latest set and sends
Character a Frame every 100 ms, moving or not, as the LD2450 does. The LD2450 actor replaces this
one and sends the same Frame.

People further from the screens than ``max_distance_m`` are dropped here, as the LD2450's own
region filter would drop them. The page's slider changes it for this connection only; venue.toml
sets where every connection starts."""

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from ohra import ActorContext, ActorRef, Behavior, Behaviors

from koi_signage.character import CharacterMsg
from koi_signage.messages import AttachFloor, Frame, Sensed, Status, Target
from koi_signage.venue import Venue, in_view

MAX_TARGETS = 3  # the LD2450 tracks at most 3 people
FRAME_INTERVAL_S = 0.1  # the LD2450 reports at about 10 fps


@dataclass(frozen=True)
class Pointer:
    """Where the page says people are: the pointer, and anyone clicked onto the floor."""

    targets: tuple[Target, ...]


@dataclass(frozen=True)
class MaxDistance:
    """From the page's slider: ignore people further from the screens than ``m`` metres."""

    m: float


@dataclass(frozen=True)
class _Tick:
    pass


@dataclass(frozen=True)
class _CharacterGone:
    pass


type FloorMsg = Pointer | MaxDistance | Status | _Tick | _CharacterGone


def finite_number(v: object) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        raise ValueError(f"not a finite number: {v!r}")
    return float(v)


def decode_floor(text: str) -> Pointer | MaxDistance:
    """``{"targets": [{"x": n, "y": n}, ...]}`` or ``{"max_distance_m": n}``. Anything else raises
    ValueError, which closes the socket with 1003."""
    doc: object = json.loads(text)
    if not isinstance(doc, dict):
        raise ValueError("expected an object")
    fields = cast(dict[str, object], doc)
    if "max_distance_m" in fields:
        return MaxDistance(finite_number(fields["max_distance_m"]))
    targets = fields.get("targets")
    if not isinstance(targets, list):
        raise ValueError("expected a list of targets")
    out: list[Target] = []
    for t in cast(list[object], targets):
        if not isinstance(t, dict):
            raise ValueError("expected a target object")
        point = cast(dict[str, object], t)
        out.append(Target(finite_number(point.get("x")), finite_number(point.get("y"))))
    return Pointer(tuple(out))


def clamp(v: Venue, targets: Sequence[Target], max_distance_m: float) -> tuple[Target, ...]:
    """Drop points off the floor, out of the radar's view or further than ``max_distance_m``,
    then keep the first 3, as the radar would."""
    reach = min(max_distance_m, v.depth_m)
    on = [t for t in targets if 0 <= t.x <= v.width_m and 0 <= t.y <= reach and in_view(v, t)]
    return tuple(on[:MAX_TARGETS])


def floor(
    venue: Venue, character: ActorRef[CharacterMsg], out: ActorRef[dict[str, Any]]
) -> Behavior[FloorMsg]:
    def setup(ctx: ActorContext[FloorMsg]) -> Behavior[FloorMsg]:
        character.tell(AttachFloor(ctx.self))
        ctx.watch_with(character, _CharacterGone())  # a new character means a fresh page
        ctx.timers.start_timer_with_fixed_delay("tick", _Tick(), FRAME_INTERVAL_S)

        def settings(reach: float) -> None:
            out.tell({"type": "settings", "max_distance_m": reach})

        def run(latest: tuple[Target, ...], reach: float) -> Behavior[FloorMsg]:
            """``latest`` is what the page sent, unfiltered, so a new reach applies to it."""

            def on_message(_ctx: ActorContext[FloorMsg], msg: FloorMsg) -> Behavior[FloorMsg]:
                match msg:
                    case Pointer(targets):
                        return run(targets, reach)
                    case MaxDistance(m):
                        m = min(max(m, 0.0), venue.depth_m)
                        settings(m)
                        return run(latest, m)
                    case _Tick():
                        character.tell(Sensed(ctx.self, Frame(clamp(venue, latest, reach))))
                        return Behaviors.same
                    case Status(mode, count, screen):
                        out.tell(
                            {"type": "status", "mode": mode, "count": count, "screen": screen}
                        )
                        return Behaviors.same
                    case _CharacterGone():
                        return Behaviors.stopped()

            return Behaviors.receive(on_message)

        settings(venue.max_distance_m)
        return run((), venue.max_distance_m)

    return Behaviors.setup(setup)
