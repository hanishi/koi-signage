from koi_signage.messages import Enter, Exit, Prepare, Ready, Status
from util import V4, Rig, people, rig


async def crowd(r: Rig) -> None:
    """Two people on screen 1 for 1 s: Crowd on screen 1."""
    r.ref.tell(people(4.0, 4.5))
    await r.floor.expect_message(Status("idle", 2, 1))
    await r.time.time_passes(1.0)
    for s in r.screens:
        await s.receive_message()  # Enter on 1, Exit on 0 and 2
    await r.floor.expect_message(Status("crowd", 2, 1))


async def hop(r: Rig, a: int, b: int) -> None:
    """Screen b is prepared, answers ready, and the character moves a → b."""
    await r.screens[b].expect_message(Prepare())
    r.ref.tell(Ready(b))
    await r.screens[a].expect_message_type(Exit)
    await r.screens[b].expect_message_type(Enter)


async def test_tie_stays() -> None:
    async with rig() as r:
        await crowd(r)
        r.ref.tell(people(0.5, 8.5))
        await r.time.time_passes(5.0)
        for s in r.screens:
            await s.expect_no_message(0)


async def test_lead_for_1s_moves_one_screen() -> None:
    async with rig() as r:
        await crowd(r)
        r.ref.tell(people(8.0, 8.5))
        await r.time.time_passes(0.9)
        await r.screens[2].expect_no_message(0)
        await r.time.time_passes(0.1)
        await hop(r, 1, 2)


async def test_linger_blocks_second_move() -> None:
    async with rig() as r:
        await crowd(r)
        r.ref.tell(people(8.0, 8.5))
        await r.time.time_passes(1.0)
        await hop(r, 1, 2)  # arrived on 2: linger for 3 s
        r.ref.tell(people(0.5, 1.0, 1.5))  # screen 0 leads now
        await r.time.time_passes(2.9)
        await r.screens[1].expect_no_message(0)
        await r.time.time_passes(0.1)
        await hop(r, 2, 1)  # one screen toward 0, not straight there
        await r.screens[0].expect_no_message(0)


async def test_leader_change_restarts_lead() -> None:
    async with rig() as r:
        await crowd(r)
        r.ref.tell(people(8.0, 8.5))
        await r.time.time_passes(0.6)
        r.ref.tell(people(0.5, 1.0))
        await r.time.time_passes(0.6)
        for s in r.screens:
            await s.expect_no_message(0)
        await r.time.time_passes(0.4)
        await r.screens[0].expect_message(Prepare())


async def test_four_screens_crowd_moves_one_screen_toward_the_leader() -> None:
    async with rig(attach=(0, 1, 2, 3), venue=V4) as r:
        await crowd(r)
        r.ref.tell(people(10.0, 10.5))  # screen 3 leads, two screens away
        await r.time.time_passes(1.0)
        await hop(r, 1, 2)
        await r.screens[3].expect_no_message(0)
