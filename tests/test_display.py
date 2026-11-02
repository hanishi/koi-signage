from typing import Any

import pytest
from ohra import ActorRef
from ohra.testkit import ActorTestKit, TestProbe

from koi_signage.character import CharacterMsg
from koi_signage.display import DisplayMsg, PageReady, Ping, decode_screen, display
from koi_signage.messages import AttachScreen, Cancel, Enter, Exit, Idle, Prepare, Ready


async def spawned(
    testkit: ActorTestKit,
) -> tuple[TestProbe[CharacterMsg], TestProbe[dict[str, Any]], ActorRef[DisplayMsg]]:
    character: TestProbe[CharacterMsg] = testkit.create_test_probe()
    out: TestProbe[dict[str, Any]] = testkit.create_test_probe()
    ref = testkit.spawn(display(2, character.ref, out.ref, clock=lambda: 42.0))
    await character.expect_message(AttachScreen(2, ref))
    return character, out, ref


async def test_attaches_on_start() -> None:
    async with ActorTestKit() as testkit:
        await spawned(testkit)  # asserts AttachScreen(2, ref)


async def test_commands_held_until_first_ping() -> None:
    """A page can't place ``t`` on its own clock before it has an offset, so nothing goes out
    before its first ping is answered: the pong first, then what was held."""
    async with ActorTestKit() as testkit:
        _, out, ref = await spawned(testkit)
        ref.tell(Enter(2.5))
        await out.expect_no_message(0.05)
        ref.tell(Ping(1.0))
        assert await out.receive_messages(2) == [
            {"type": "pong", "c": 1.0, "s": 42.0},
            {"type": "enter", "t": 2.5, "side": None},
        ]


async def test_commands_to_json() -> None:
    async with ActorTestKit() as testkit:
        _, out, ref = await spawned(testkit)
        ref.tell(Ping(0.0))
        await out.receive_message()
        for cmd in (Idle(), Prepare(), Cancel(), Enter(2.5, "left"), Exit(3.0)):
            ref.tell(cmd)
        assert await out.receive_messages(5) == [
            {"type": "idle"},
            {"type": "prepare"},
            {"type": "cancel"},
            {"type": "enter", "t": 2.5, "side": "left"},
            {"type": "exit", "t": 3.0, "side": None},
        ]


async def test_ready_relayed_as_ready_n() -> None:
    async with ActorTestKit() as testkit:
        character, _, ref = await spawned(testkit)
        ref.tell(PageReady())
        await character.expect_message(Ready(2))


async def test_pong_uses_clock() -> None:
    async with ActorTestKit() as testkit:
        _, out, ref = await spawned(testkit)
        ref.tell(Ping(1.5))
        await out.expect_message({"type": "pong", "c": 1.5, "s": 42.0})


def test_decode_screen() -> None:
    assert decode_screen('{"type": "ready"}') == PageReady()
    assert decode_screen('{"type": "ping", "c": 1.5}') == Ping(1.5)


@pytest.mark.parametrize(
    "text", ['{"type": "ping", "c": NaN}', '{"type": "ping"}', '{"type": "x"}', "[]", "nope"]
)
def test_decode_screen_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        decode_screen(text)


async def test_stops_when_character_stops() -> None:
    async with ActorTestKit() as testkit:
        character, _, ref = await spawned(testkit)
        watcher: TestProbe[None] = testkit.create_test_probe()
        character.stop()
        await watcher.expect_terminated(ref)
