"""The messages between the venue's actors. Character's private timer and watch messages live in
``character.py``."""

from dataclasses import dataclass
from typing import Literal

from ohra import ActorRef

from signage.venue import Target

__all__ = [
    "AttachFloor",
    "AttachScreen",
    "Cancel",
    "Enter",
    "Exit",
    "Frame",
    "Idle",
    "Mode",
    "Prepare",
    "Ready",
    "ScreenCmd",
    "Status",
    "Target",
]

type Mode = Literal["idle", "follow", "crowd"]


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
    """Show the character at ``t``, on the venue's monotonic clock."""

    t: float


@dataclass(frozen=True)
class Exit:
    """Stop showing it at ``t``."""

    t: float


type ScreenCmd = Idle | Prepare | Cancel | Enter | Exit


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
class Status:
    mode: Mode
    count: int
    screen: int


@dataclass(frozen=True)
class AttachFloor:
    ref: ActorRef[Status]
