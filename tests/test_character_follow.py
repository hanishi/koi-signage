from signage.character import follow_step
from signage.messages import Cancel, Enter, Exit, Prepare, Ready, Status
from util import V, people, rig


def test_follow_step() -> None:  # boundaries at 3 and 6, dead zone 0.3
    assert follow_step(V, 1, 4.5) == ("stay", 1)
    assert follow_step(V, 1, 3.2) == ("prepare", 0)
    assert follow_step(V, 1, 2.8) == ("prepare", 0)
    assert follow_step(V, 1, 2.6) == ("handoff", 0)
    assert follow_step(V, 1, 6.31) == ("handoff", 2)
    assert follow_step(V, 0, 8.0) == ("handoff", 1)
    assert follow_step(V, 0, 1.0) == ("stay", 0)
    assert follow_step(V, 2, 6.2) == ("prepare", 1)


async def test_band_prepare_then_turn_back_cancels() -> None:
    async with rig() as r:
        await r.follow()
        r.ref.tell(people(3.2))
        await r.screens[0].expect_message(Prepare())
        r.ref.tell(people(4.5))
        await r.screens[0].expect_message(Cancel())


async def test_crossing_hands_off_with_same_t() -> None:
    async with rig() as r:
        await r.follow()
        r.ref.tell(people(3.2))
        await r.screens[0].expect_message(Prepare())
        r.ref.tell(Ready(0))
        r.ref.tell(people(2.5))
        t = r.now() + V.handoff_lead_s
        await r.screens[1].expect_message(Exit(t))
        await r.screens[0].expect_message(Enter(t))
        await r.floor.expect_message(Status("follow", 1, 0))


async def test_handoff_without_ready_times_out() -> None:
    async with rig() as r:
        await r.follow()
        r.ref.tell(people(2.5))
        await r.screens[0].expect_message(Prepare())
        await r.time.time_passes(0.9)
        await r.screens[1].expect_no_message(0)
        await r.time.time_passes(0.1)
        t = r.now() + V.handoff_lead_s
        await r.screens[1].expect_message(Exit(t))
        await r.screens[0].expect_message(Enter(t))


async def test_jitter_inside_band_sends_one_prepare() -> None:
    async with rig() as r:
        await r.follow()
        for x in (3.2, 2.9, 3.1, 2.8):
            r.ref.tell(people(x))
        await r.screens[0].expect_message(Prepare())
        await r.time.time_passes(0.5)
        for s in r.screens:
            await s.expect_no_message(0)


async def test_far_target_steps_one_screen() -> None:
    async with rig() as r:
        await r.follow()
        r.ref.tell(people(1.0))  # over to screen 0 first
        await r.screens[0].expect_message(Prepare())
        r.ref.tell(Ready(0))
        await r.screens[1].expect_message_type(Exit)
        await r.screens[0].expect_message_type(Enter)
        r.ref.tell(people(8.0))  # far right: one screen at a time
        await r.screens[1].expect_message(Prepare())
        r.ref.tell(Ready(1))
        await r.screens[0].expect_message_type(Exit)
        await r.screens[1].expect_message_type(Enter)
        await r.screens[2].expect_no_message(0)
        r.ref.tell(people(8.0))  # the next frame takes the next step
        await r.screens[2].expect_message(Prepare())


async def test_handoff_to_detached_screen_moves() -> None:
    async with rig(attach=(1, 2)) as r:
        await r.follow()
        r.ref.tell(people(2.5))
        await r.screens[1].expect_message(Exit(r.now() + V.handoff_lead_s))
        await r.floor.expect_message(Status("follow", 1, 0))


async def test_mode_change_cancels_prepare() -> None:
    async with rig() as r:
        await r.follow()
        r.ref.tell(people(3.2))
        await r.screens[0].expect_message(Prepare())
        r.ref.tell(people(3.2, 8.0))  # two people: no follow decisions, Crowd after 1 s
        await r.time.time_passes(1.0)
        await r.screens[0].expect_message(Cancel())
