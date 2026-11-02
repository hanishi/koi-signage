from typing import Any

import pytest
from ohra.testkit import ActorTestKit, ManualTime, TestProbe

from koi_signage.character import CharacterMsg
from koi_signage.floor import MaxDistance, Pointer, clamp, decode_floor, floor
from koi_signage.messages import AttachFloor, Frame, Sensed, Status, Target
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
        '{"max_distance_m": NaN}',
        '{"max_distance_m": "2"}',
    ],
)
def test_decode_floor_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        decode_floor(text)


def test_decode_floor_accepts() -> None:
    text = '{"targets": [{"x": 4, "y": 1.5}]}'
    assert decode_floor(text) == Pointer((Target(4, 1.5),))
    assert decode_floor('{"max_distance_m": 2.5}') == MaxDistance(2.5)


def test_clamp() -> None:
    five = [Target(x, 1) for x in (3.5, 4, 4.5, 5, 5.5)]
    assert clamp(V, five, 4) == tuple(five[:3])
    off = [Target(-0.1, 1), Target(1, 4.1), Target(9.1, 1), Target(1, -0.1), Target(4.5, 4)]
    assert clamp(V, off, 4) == (Target(4.5, 4),)


def test_clamp_keeps_only_what_the_radar_sees() -> None:
    """The LD2450 at x = 4.5 m on the screen line sees ±60° out to 6 m."""
    beside = Target(1.0, 0.5)  # 82° off straight out: close to screen 0, but out of view
    wide = Target(1.0, 3.0)  # 49° off, 4.6 m away: seen
    corner = Target(9.0, 4.0)  # 6.02 m away: out of range
    ahead = Target(4.5, 0.0)  # right in front of the sensor: seen
    assert clamp(V, [beside, wide, corner, ahead], 4) == (wide, ahead)


def test_clamp_drops_people_beyond_max_distance_before_taking_3() -> None:
    near, far = [Target(x, 1) for x in (4, 4.5, 5)], [Target(5, 2.5), Target(6, 2.01)]
    assert clamp(V, [*far, *near], 2.0) == tuple(near)
    assert clamp(V, [Target(4, 2.0)], 2.0) == (Target(4, 2.0),)  # on the line still counts


async def spawned(
    testkit: ActorTestKit,
) -> tuple[TestProbe[CharacterMsg], TestProbe[dict[str, Any]], Any]:
    character: TestProbe[CharacterMsg] = testkit.create_test_probe()
    out: TestProbe[dict[str, Any]] = testkit.create_test_probe()
    ref = testkit.spawn(floor(V, character.ref, out.ref))
    await character.expect_message(AttachFloor(ref))
    await out.expect_message({"type": "settings", "max_distance_m": V.max_distance_m})
    return character, out, ref


async def test_frames_every_100ms_without_input() -> None:
    async with ActorTestKit(manual_time=True) as testkit:
        character, _, ref = await spawned(testkit)
        await ManualTime(testkit.system).time_passes(0.3)
        assert await character.receive_messages(3) == [Sensed(ref, Frame(()))] * 3
        await character.expect_no_message(0)


async def test_pointer_then_frame() -> None:
    async with ActorTestKit(manual_time=True) as testkit:
        character, _, ref = await spawned(testkit)
        ref.tell(Pointer((Target(4, 1), Target(-1, 1))))
        await ManualTime(testkit.system).time_passes(0.1)
        await character.expect_message(Sensed(ref, Frame((Target(4, 1),))))


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


async def test_max_distance_from_the_page_takes_effect_and_is_echoed() -> None:
    async with ActorTestKit(manual_time=True) as testkit:
        character, out, ref = await spawned(testkit)
        ref.tell(Pointer((Target(4, 1), Target(5, 2))))
        ref.tell(MaxDistance(1.5))
        await out.expect_message({"type": "settings", "max_distance_m": 1.5})
        await ManualTime(testkit.system).time_passes(0.1)
        await character.expect_message(Sensed(ref, Frame((Target(4, 1),))))


async def test_max_distance_kept_on_the_floor() -> None:
    async with ActorTestKit(manual_time=True) as testkit:
        _, out, ref = await spawned(testkit)
        ref.tell(MaxDistance(99))
        await out.expect_message({"type": "settings", "max_distance_m": V.depth_m})
        ref.tell(MaxDistance(-1))
        await out.expect_message({"type": "settings", "max_distance_m": 0.0})
