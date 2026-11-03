"""The character: the only actor in the venue that decides anything.

It idles when nobody is there, follows one person from screen to screen, and moves toward the
busiest screen when there are several. An ad interrupts all of that: every screen plays it, and
when its slot is over they show the character again. Every threshold runs on ohra timers."""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Literal

from ohra import ActorContext, ActorRef, Behavior, Behaviors, TimerScheduler

from koi_signage.messages import (
    Ad,
    AttachFloor,
    AttachScreen,
    Cancel,
    Enter,
    Exit,
    Frame,
    Idle,
    Mode,
    PlayAd,
    Prepare,
    Ready,
    ScreenCmd,
    Sensed,
    Status,
)
from koi_signage.venue import Venue, boundaries, screen_counts

# An ad starts this long after it is asked for, on every screen at once: time for the tablets to
# load the clip while the creative fades out (1 s, in screen.js). Under the 2 s a screen accepts
# as ahead of its clock; a tablet that is slower to load starts the clip part way, in step.
AD_LEAD_S = 1.5


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


@dataclass(frozen=True)
class _ReadyTimeout:
    n: int


@dataclass(frozen=True)
class _LingerDone:
    pass


@dataclass(frozen=True)
class _LeadDone:
    screen: int


@dataclass(frozen=True)
class _AdDone:
    t: float  # the ad's start: a replaced ad's timer is stale


type CharacterMsg = (
    Frame
    | Sensed
    | AttachScreen
    | Ready
    | AttachFloor
    | _Settle
    | _ScreenGone
    | _FloorGone
    | _ReadyTimeout
    | _LingerDone
    | _LeadDone
    | Ad
    | _AdDone
)

_MODE: Mapping[int, Mode] = {0: "idle", 1: "follow", 2: "crowd"}


@dataclass(frozen=True)
class _State:
    mode: Mode = "idle"
    screen: int = 1
    count: int = 0
    # every page showing screen n gets its commands: a tablet and the laptop's view, say
    screens: Mapping[int, tuple[ActorRef[ScreenCmd], ...]] = field(
        default_factory=dict[int, tuple[ActorRef[ScreenCmd], ...]]
    )
    # every floor page gets Status; only the newest one's frames drive the character
    floors: tuple[ActorRef[Status], ...] = ()
    settling: int | None = None  # the `seen` the settle timer is running for
    shown: Status | None = None  # the last Status the floors got
    prepared: int | None = None  # the screen told Prepare
    ready: int | None = None  # the prepared screen, once it answered Ready
    moving: int | None = None  # a handoff waiting for Ready or the timeout
    lead: int | None = None  # the screen leading the crowd, other than the character's
    lead_due: bool = False  # it has led for crowd_lead_s
    ad: PlayAd | None = None  # the ad every screen is playing: the people are not shown


def follow_step(
    v: Venue, screen: int, x: float
) -> tuple[Literal["stay", "prepare", "handoff"], int]:
    """What one person at ``x`` asks of a character on ``screen``. Within ``dead_zone_m`` of a
    boundary it prepares the neighbour; beyond the band it hands off. A target further away
    still gets a handoff to the neighbour, so the character crosses one screen at a time."""
    cuts = boundaries(v)
    for n in (screen - 1, screen + 1):
        if not 0 <= n < v.screens:
            continue
        b = cuts[min(screen, n)]
        d = x - b if n > screen else b - x  # > 0: on n's side
        if d > v.dead_zone_m:
            return "handoff", n
        if d >= -v.dead_zone_m:
            return "prepare", n
    return "stay", screen


def character(venue: Venue, clock: Callable[[], float] = time.monotonic) -> Behavior[CharacterMsg]:
    """``clock`` stamps Enter and Exit. It must be the clock Display answers pings with."""
    threshold = {0: venue.idle_after_s, 1: venue.follow_after_s, 2: venue.crowd_after_s}

    def setup(timers: TimerScheduler[CharacterMsg]) -> Behavior[CharacterMsg]:
        def tell(s: _State, n: int, cmd: ScreenCmd) -> None:
            for ref in s.screens.get(n, ()):
                ref.tell(cmd)

        def current(s: _State, n: int) -> ScreenCmd:
            if s.ad is not None:
                return s.ad
            if s.mode == "idle":
                return Idle()
            return Enter(clock()) if n == s.screen else Exit(clock())

        def unprepare(s: _State) -> _State:
            if s.prepared is not None:
                tell(s, s.prepared, Cancel())
            timers.cancel("ready")
            return replace(s, prepared=None, ready=None, moving=None)

        def prepare(s: _State, n: int) -> _State:
            if s.prepared == n:
                return s
            s = unprepare(s)
            tell(s, n, Prepare())
            return replace(s, prepared=n)

        def complete(s: _State, n: int) -> _State:
            t = clock() + venue.handoff_lead_s
            rightward = n > s.screen  # screens are numbered from the left
            tell(s, s.screen, Exit(t, "right" if rightward else "left"))
            tell(s, n, Enter(t, "left" if rightward else "right"))
            timers.cancel("ready")
            timers.start_single_timer("linger", _LingerDone(), venue.linger_s)
            return replace(s, screen=n, prepared=None, ready=None, moving=None)

        def handoff(s: _State, n: int) -> _State:
            if s.ready == n or not s.screens.get(n):
                return complete(s, n)
            s = prepare(s, n)
            timers.start_single_timer("ready", _ReadyTimeout(n), venue.ready_timeout_s)
            return replace(s, moving=n)

        def follow(s: _State, x: float) -> _State:
            match follow_step(venue, s.screen, x):
                case "stay", _:
                    return unprepare(s)
                case "prepare", n:
                    return prepare(s, n)
                case "handoff", n:
                    return handoff(s, n)

        def crowd(s: _State, frame: Frame) -> _State:
            counts = screen_counts(venue, frame.targets)
            most = max(counts)
            leader = counts.index(most) if counts.count(most) == 1 else None  # a tie: no leader
            if leader is None or leader == s.screen:
                timers.cancel("lead")
                return replace(s, lead=None, lead_due=False)
            if s.lead != leader:
                timers.start_single_timer("lead", _LeadDone(leader), venue.crowd_lead_s)
                return replace(s, lead=leader, lead_due=False)
            return s

        def try_move(s: _State) -> _State:
            """One screen toward a leader that has led long enough, once the character has
            lingered where it is."""
            if (
                s.mode != "crowd"
                or s.lead is None
                or not s.lead_due
                or s.moving is not None
                or s.ad is not None
                or timers.is_timer_active("linger")
            ):
                return s
            step = s.screen + (1 if s.lead > s.screen else -1)
            # the next frame re-arms the lead if the leader is still elsewhere
            return handoff(replace(s, lead=None, lead_due=False), step)

        def enter_mode(s: _State, mode: Mode) -> _State:
            was = s.mode
            timers.cancel("lead")
            s = replace(unprepare(s), mode=mode, settling=None, lead=None, lead_due=False)
            if s.ad is None and (mode == "idle" or was == "idle"):
                for n in s.screens:
                    tell(s, n, current(s, n))
            return s

        def settle(s: _State) -> _State:
            seen = min(s.count, 2)
            if _MODE[seen] == s.mode:
                timers.cancel("settle")
                return replace(s, settling=None)
            if s.settling != seen:
                timers.start_single_timer("settle", _Settle(seen), threshold[seen])
                return replace(s, settling=seen)
            return s

        def on_frame(s: _State, frame: Frame) -> _State:
            s = settle(replace(s, count=len(frame.targets)))
            if s.moving is not None or s.ad is not None:
                return s
            if s.mode == "follow" and s.count == 1:
                return follow(s, frame.targets[0].x)
            if s.mode == "crowd":
                return crowd(s, frame)
            return s

        def publish(s: _State) -> _State:
            status = Status("ad" if s.ad else s.mode, s.count, s.screen)
            if status == s.shown:
                return s
            for floor in s.floors:
                floor.tell(status)
            return replace(s, shown=status)

        def step(ctx: ActorContext[CharacterMsg], s: _State, msg: CharacterMsg) -> _State:
            match msg:
                case Frame():  # the radar
                    return on_frame(s, msg)
                case Sensed(floor, frame):
                    return on_frame(s, frame) if s.floors[-1:] == (floor,) else s
                case _Settle(seen):
                    return enter_mode(s, _MODE[seen]) if seen == s.settling else s
                case AttachScreen(n, ref):
                    ctx.watch_with(ref, _ScreenGone(n, ref))
                    pages = tuple(p for p in s.screens.get(n, ()) if p != ref) + (ref,)
                    ref.tell(current(s, n))
                    return replace(s, screens={**s.screens, n: pages})
                case _ScreenGone(n, ref):
                    pages = tuple(p for p in s.screens.get(n, ()) if p != ref)
                    rest = {k: v for k, v in s.screens.items() if k != n}
                    return replace(s, screens={**rest, n: pages} if pages else rest)
                case AttachFloor(ref):
                    ctx.watch_with(ref, _FloorGone(ref))
                    status = Status("ad" if s.ad else s.mode, s.count, s.screen)
                    ref.tell(status)
                    floors = tuple(f for f in s.floors if f != ref) + (ref,)
                    return replace(s, floors=floors, shown=status)
                case _FloorGone(ref):
                    s = replace(s, floors=tuple(f for f in s.floors if f != ref))
                    if s.floors:  # the next newest floor's frames drive it now
                        return s
                    # no sensor is the same as nobody there: Idle after idle_after_s
                    return on_frame(s, Frame(()))
                case Ready(n):
                    if s.moving == n:
                        return complete(s, n)
                    return replace(s, ready=n) if s.prepared == n else s
                case _ReadyTimeout(n):
                    return complete(s, n) if s.moving == n else s
                case _LingerDone():
                    return try_move(s)
                case _LeadDone(n):
                    return try_move(replace(s, lead_due=True)) if n == s.lead else s
                case Ad(clip, seconds):
                    timers.cancel("lead")
                    ad = PlayAd(clip, clock() + AD_LEAD_S)
                    s = replace(unprepare(s), ad=ad, lead=None, lead_due=False)
                    for n in s.screens:
                        tell(s, n, ad)
                    timers.start_single_timer("ad", _AdDone(ad.t), AD_LEAD_S + seconds)
                    return s
                case _AdDone(t):
                    if s.ad is None or s.ad.t != t:
                        return s
                    s = replace(s, ad=None)
                    for n in s.screens:  # the koi come back where the people are
                        tell(s, n, current(s, n))
                    return s

        def run(s: _State) -> Behavior[CharacterMsg]:
            def on_message(
                ctx: ActorContext[CharacterMsg], msg: CharacterMsg
            ) -> Behavior[CharacterMsg]:
                return run(publish(step(ctx, s, msg)))

            return Behaviors.receive(on_message)

        return run(_State(screen=(venue.screens - 1) // 2))  # start in the middle

    return Behaviors.with_timers(setup)
