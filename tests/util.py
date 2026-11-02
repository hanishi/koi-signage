"""A character on the repo's venue, on a manual clock, with probes for its screens and floor."""

from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ohra import ActorRef
from ohra.testkit import ActorTestKit, ManualTime, TestProbe

from signage.character import CharacterMsg, character
from signage.messages import (
    AttachFloor,
    AttachScreen,
    Enter,
    Exit,
    Frame,
    Idle,
    ScreenCmd,
    Status,
    Target,
)
from signage.venue import load_venue

V = load_venue(Path(__file__).parent.parent / "venue.toml")


def people(*xs: float) -> Frame:
    return Frame(tuple(Target(x, 1.0) for x in xs))


@dataclass
class Rig:
    testkit: ActorTestKit
    time: ManualTime
    ref: ActorRef[CharacterMsg]
    screens: list[TestProbe[ScreenCmd]]
    attached: Sequence[int]
    floor: TestProbe[Status]

    def now(self) -> float:
        return self.time.scheduler.current_time

    def attach(self, n: int) -> TestProbe[ScreenCmd]:
        """A new probe attached as screen ``n``; its first message is left for the test."""
        probe: TestProbe[ScreenCmd] = self.testkit.create_test_probe()
        self.ref.tell(AttachScreen(n, probe.ref))
        return probe

    async def kill(self, probe: TestProbe[Any]) -> None:
        """Stop ``probe`` (a tablet or floor page going away) and wait until it has."""
        watcher: TestProbe[None] = self.testkit.create_test_probe()
        probe.stop()
        await watcher.expect_terminated(probe.ref)

    async def follow(self, x: float = 4.0) -> None:
        """One person at ``x`` (screen 1) for 1 s: the character enters Follow on screen 1.
        Drains what the screens and the floor got on the way."""
        self.ref.tell(people(x))
        await self.floor.expect_message(Status("idle", 1, 1))
        await self.time.time_passes(V.follow_after_s)
        t = self.now()
        for n in self.attached:
            await self.screens[n].expect_message(Enter(t) if n == 1 else Exit(t))
        await self.floor.expect_message(Status("follow", 1, 1))


@asynccontextmanager
async def rig(attach: Sequence[int] = (0, 1, 2)) -> AsyncGenerator[Rig]:
    async with ActorTestKit(manual_time=True) as testkit:
        time = ManualTime(testkit.system)
        ref = testkit.spawn(character(V, clock=lambda: time.scheduler.current_time))
        screens: list[TestProbe[ScreenCmd]] = [testkit.create_test_probe() for _ in range(3)]
        floor: TestProbe[Status] = testkit.create_test_probe()
        ref.tell(AttachFloor(floor.ref))
        await floor.expect_message(Status("idle", 0, 1))
        for n in attach:
            ref.tell(AttachScreen(n, screens[n].ref))
            await screens[n].expect_message(Idle())
        yield Rig(testkit, time, ref, screens, attach, floor)
