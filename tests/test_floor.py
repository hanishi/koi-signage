from typing import Any

import pytest
from ohra.testkit import ActorTestKit, ManualTime, TestProbe

from signage.character import CharacterMsg
from signage.floor import Pointer, clamp, decode_floor, floor
from signage.messages import AttachFloor, Frame, Status, Target
from util import V


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"targets": [{"x": NaN, "y": 1}]}',
        '{"targets": [{"x": Infinity, "y": 1}]}',
        '{"targets": [{"x": "1", "y": 1}]}',
        '{"targets": [{"x": true, "y": 1}]}',
        '{"targets": [{"x": 1}]}',
        '{"targets": [3]}',
        '{"targets": 3}',
        "[]",
    ],
)
def test_decode_floor_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        decode_floor(text)


def test_decode_floor_accepts() -> None:
    text = '{"targets": [{"x": 4, "y": 1.5}]}'
    assert decode_floor(text) == Pointer((Target(4, 1.5),))


def test_clamp() -> None:
    five = [Target(x, 1) for x in (1, 2, 3, 4, 5)]
    assert clamp(V, five) == tuple(five[:3])
    off = [Target(-0.1, 1), Target(1, 4.1), Target(9.1, 1), Target(1, -0.1), Target(9, 4)]
    assert clamp(V, off) == (Target(9, 4),)


async def spawned(
    testkit: ActorTestKit,
) -> tuple[TestProbe[CharacterMsg], TestProbe[dict[str, Any]], Any]:
    character: TestProbe[CharacterMsg] = testkit.create_test_probe()
    out: TestProbe[dict[str, Any]] = testkit.create_test_probe()
    ref = testkit.spawn(floor(V, character.ref, out.ref))
    await character.expect_message(AttachFloor(ref))
    return character, out, ref


async def test_frames_every_100ms_without_input() -> None:
    async with ActorTestKit(manual_time=True) as testkit:
        character, _, _ = await spawned(testkit)
        await ManualTime(testkit.system).time_passes(0.3)
        assert await character.receive_messages(3) == [Frame(())] * 3
        await character.expect_no_message(0)


async def test_pointer_then_frame() -> None:
    async with ActorTestKit(manual_time=True) as testkit:
        character, _, ref = await spawned(testkit)
        ref.tell(Pointer((Target(4, 1), Target(-1, 1))))
        await ManualTime(testkit.system).time_passes(0.1)
        await character.expect_message(Frame((Target(4, 1),)))


async def test_status_forwarded() -> None:
    async with ActorTestKit(manual_time=True) as testkit:
        _, out, ref = await spawned(testkit)
        ref.tell(Status("follow", 1, 1))
        await out.expect_message({"type": "status", "mode": "follow", "count": 1, "screen": 1})


async def test_stops_when_character_stops() -> None:
    async with ActorTestKit(manual_time=True) as testkit:
        character, _, ref = await spawned(testkit)
        watcher: TestProbe[None] = testkit.create_test_probe()
        character.stop()
        await watcher.expect_terminated(ref)
