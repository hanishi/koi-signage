"""The messages between the venue's actors. Character's private timer and watch messages live in
``character.py``."""

from dataclasses import dataclass
from typing import Literal

from ohra import ActorRef

from koi_signage.venue import Target

__all__ = [
    "Ad",
    "AttachFloor",
    "AttachScreen",
    "Cancel",
    "Enter",
    "Exit",
    "Frame",
    "Idle",
    "Mode",
    "PlayAd",
    "Prepare",
    "Ready",
    "ScreenCmd",
    "Sensed",
    "Side",
    "Status",
    "Target",
]

type Mode = Literal["idle", "follow", "crowd"]  # what the people on the floor ask for
type Side = Literal["left", "right"]


@dataclass(frozen=True)
class Frame:
    """One sensor reading: everyone on the floor right now, at most 3, as the LD2450 reports."""

    targets: tuple[Target, ...]


# --- Character → a screen ----------------------------------------------------------------------


@dataclass(frozen=True)
class Idle:
    """Play the attract loop."""


@dataclass(frozen=True)
class Prepare:
    """The character may arrive soon: load its assets, then answer ready."""


@dataclass(frozen=True)
class Cancel:
    """It won't arrive after all."""


@dataclass(frozen=True)
class Enter:
    """Show the character at ``t``, on the venue's monotonic clock. On a handoff, ``side`` is
    the edge it comes in from, the one facing the screen it left; otherwise it just appears."""

    t: float
    side: Side | None = None


@dataclass(frozen=True)
class Exit:
    """Stop showing it at ``t``. On a handoff, ``side`` is the edge it leaves through."""

    t: float
    side: Side | None = None


@dataclass(frozen=True)
class PlayAd:
    """Play ``clip`` from ``t``, muted, in place of the creative, which fades out before it. A
    screen that gets this after ``t`` starts the clip part way, where the other screens are."""

    clip: str
    t: float


type ScreenCmd = Idle | Prepare | Cancel | Enter | Exit | PlayAd


# --- to Character ------------------------------------------------------------------------------


@dataclass(frozen=True)
class AttachScreen:
    n: int
    ref: ActorRef[ScreenCmd]


@dataclass(frozen=True)
class Ready:
    """Screen ``n`` has loaded what Prepare asked for."""

    n: int


@dataclass(frozen=True)
class Ad:
    """Interrupt: every screen plays ``clip`` for ``seconds``, then shows the character again."""

    clip: str
    seconds: float


@dataclass(frozen=True)
class Status:
    mode: Mode | Literal["ad"]
    count: int
    screen: int


@dataclass(frozen=True)
class AttachFloor:
    ref: ActorRef[Status]


@dataclass(frozen=True)
class Sensed:
    """A Frame from one floor page. Only the newest floor page drives the character; the radar
    sends plain Frames."""

    floor: ActorRef[Status]
    frame: Frame
