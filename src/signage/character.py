"""The character: the only actor in the venue that decides anything.

It idles when nobody is there, follows one person from screen to screen, and moves toward the
busiest screen when there are several. Every threshold runs on ohra timers."""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace

from ohra import ActorContext, ActorRef, Behavior, Behaviors, TimerScheduler

from signage.messages import (
    AttachFloor,
    AttachScreen,
    Enter,
    Exit,
    Frame,
    Idle,
    Mode,
    Ready,
    ScreenCmd,
    Status,
)
from signage.venue import Venue


@dataclass(frozen=True)
class _Settle:
    seen: int


@dataclass(frozen=True)
class _ScreenGone:
    n: int
    ref: ActorRef[ScreenCmd]


@dataclass(frozen=True)
class _FloorGone:
    ref: ActorRef[Status]


type CharacterMsg = Frame | AttachScreen | Ready | AttachFloor | _Settle | _ScreenGone | _FloorGone

_MODE: Mapping[int, Mode] = {0: "idle", 1: "follow", 2: "crowd"}


@dataclass(frozen=True)
class _State:
    mode: Mode = "idle"
    screen: int = 1
    count: int = 0
    screens: Mapping[int, ActorRef[ScreenCmd]] = field(
        default_factory=dict[int, ActorRef[ScreenCmd]]
    )
    floor: ActorRef[Status] | None = None
    settling: int | None = None  # the `seen` the settle timer is running for
    shown: Status | None = None  # the last Status the floor got


def character(venue: Venue, clock: Callable[[], float] = time.monotonic) -> Behavior[CharacterMsg]:
    """``clock`` stamps Enter and Exit. It must be the clock Display answers pings with."""
    threshold = {0: venue.idle_after_s, 1: venue.follow_after_s, 2: venue.crowd_after_s}

    def setup(timers: TimerScheduler[CharacterMsg]) -> Behavior[CharacterMsg]:
        def tell(s: _State, n: int, cmd: ScreenCmd) -> None:
            if (ref := s.screens.get(n)) is not None:
                ref.tell(cmd)

        def current(s: _State, n: int) -> ScreenCmd:
            if s.mode == "idle":
                return Idle()
            return Enter(clock()) if n == s.screen else Exit(clock())

        def enter_mode(s: _State, mode: Mode) -> _State:
            was = s.mode
            s = replace(s, mode=mode, settling=None)
            if mode == "idle" or was == "idle":
                for n in s.screens:
                    tell(s, n, current(s, n))
            return s

        def on_frame(s: _State, frame: Frame) -> _State:
            s = replace(s, count=len(frame.targets))
            seen = min(s.count, 2)
            if _MODE[seen] == s.mode:
                timers.cancel("settle")
                return replace(s, settling=None)
            if s.settling != seen:
                timers.start_single_timer("settle", _Settle(seen), threshold[seen])
                return replace(s, settling=seen)
            return s

        def publish(s: _State) -> _State:
            status = Status(s.mode, s.count, s.screen)
            if s.floor is None or status == s.shown:
                return s
            s.floor.tell(status)
            return replace(s, shown=status)

        def step(ctx: ActorContext[CharacterMsg], s: _State, msg: CharacterMsg) -> _State:
            match msg:
                case Frame():
                    return on_frame(s, msg)
                case _Settle(seen):
                    return enter_mode(s, _MODE[seen]) if seen == s.settling else s
                case AttachScreen(n, ref):
                    ctx.watch_with(ref, _ScreenGone(n, ref))
                    s = replace(s, screens={**s.screens, n: ref})
                    ref.tell(current(s, n))
                    return s
                case _ScreenGone(n, ref):
                    if s.screens.get(n) != ref:  # an older tablet for n: the newer one stays
                        return s
                    return replace(s, screens={k: v for k, v in s.screens.items() if k != n})
                case AttachFloor(ref):
                    ctx.watch_with(ref, _FloorGone(ref))
                    return replace(s, floor=ref, shown=None)
                case _FloorGone(ref):
                    if ref != s.floor:
                        return s
                    # no sensor is the same as nobody there: Idle after idle_after_s
                    return on_frame(replace(s, floor=None, shown=None), Frame(()))
                case Ready():
                    return s

        def run(s: _State) -> Behavior[CharacterMsg]:
            def on_message(
                ctx: ActorContext[CharacterMsg], msg: CharacterMsg
            ) -> Behavior[CharacterMsg]:
                return run(publish(step(ctx, s, msg)))

            return Behaviors.receive(on_message)

        return run(_State())

    return Behaviors.with_timers(setup)
