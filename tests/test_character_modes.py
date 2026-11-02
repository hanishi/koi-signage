from ohra.testkit import TestProbe

from koi_signage.messages import AttachFloor, Enter, Exit, Idle, Sensed, Status
from util import people, rig


async def test_one_person_for_1s_follows() -> None:
    async with rig() as r:
        await r.follow()  # asserts Enter on 1, Exit on 0 and 2, Status("follow", 1, 1)


async def test_flicker_stays_idle() -> None:
    async with rig() as r:
        r.ref.tell(people(4.0))
        await r.time.time_passes(0.5)
        r.ref.tell(people())
        await r.time.time_passes(1.0)
        for s in r.screens:
            await s.expect_no_message(0)


async def test_two_for_1s_crowd() -> None:
    async with rig() as r:
        r.ref.tell(people(4.0, 4.5))
        await r.floor.expect_message(Status("idle", 2, 1))
        await r.time.time_passes(1.0)
        await r.floor.expect_message(Status("crowd", 2, 1))
        await r.screens[1].expect_message(Enter(1.0))
        await r.screens[0].expect_message(Exit(1.0))


async def test_zero_for_3s_idles() -> None:
    async with rig() as r:
        await r.follow()
        r.ref.tell(people())
        await r.time.time_passes(3.0)
        for s in r.screens:
            await s.expect_message(Idle())
        await r.floor.expect_message(Status("follow", 0, 1))
        await r.floor.expect_message(Status("idle", 0, 1))


async def test_zero_for_2_9s_then_one_stays() -> None:
    async with rig() as r:
        await r.follow()
        r.ref.tell(people())
        await r.time.time_passes(2.9)
        r.ref.tell(people(4.0))
        await r.time.time_passes(1.0)
        for s in r.screens:
            await s.expect_no_message(0)


async def test_attach_gets_current_state() -> None:
    async with rig(attach=(1,)) as r:
        await r.follow()
        t = r.now()
        await r.attach(1).expect_message(Enter(t))
        await r.attach(0).expect_message(Exit(t))
    async with rig(attach=()) as r:
        await r.attach(2).expect_message(Idle())


async def test_stopped_screen_gets_nothing() -> None:
    async with rig() as r:
        dead = r.testkit.create_dead_letter_probe()
        await r.kill(r.screens[0])
        r.attached = (1, 2)
        await r.follow()
        await dead.expect_no_message(0)


async def test_mirrored_screens_both_get_commands() -> None:
    async with rig() as r:
        mirror = r.attach(0)  # the laptop page and a tablet, both on screen 0
        await mirror.expect_message(Idle())
        await r.follow()  # asserts the first page on 0 gets Exit
        await mirror.expect_message(Exit(r.now()))


async def test_newer_mirror_leaving_keeps_the_older() -> None:
    async with rig() as r:
        newer = r.attach(0)
        await newer.expect_message(Idle())
        await r.kill(newer)  # the laptop page closes; the tablet stays
        await r.follow()  # asserts the older page on 0 still gets Exit


async def test_older_mirror_leaving_keeps_the_newer() -> None:
    async with rig() as r:
        newer = r.attach(0)
        await newer.expect_message(Idle())
        await r.kill(r.screens[0])
        r.screens[0] = newer
        await r.follow()  # asserts the newer page on 0 gets Exit


async def test_older_floor_frames_ignored() -> None:
    async with rig() as r:
        newer: TestProbe[Status] = r.testkit.create_test_probe()
        r.ref.tell(AttachFloor(newer.ref))
        await newer.expect_message(Status("idle", 0, 1))
        r.ref.tell(Sensed(r.floor.ref, people(4.0)))  # an old tab still sending
        r.ref.tell(Sensed(newer.ref, people()))
        await r.time.time_passes(1.0)
        for s in r.screens:
            await s.expect_no_message(0)
        r.ref.tell(Sensed(newer.ref, people(4.0)))
        await r.time.time_passes(1.0)
        await r.screens[1].expect_message(Enter(r.now()))
        await newer.expect_message(Status("idle", 1, 1))
        await newer.expect_message(Status("follow", 1, 1))


async def test_newer_floor_gone_older_takes_over() -> None:
    async with rig() as r:
        newer: TestProbe[Status] = r.testkit.create_test_probe()
        r.ref.tell(AttachFloor(newer.ref))
        await newer.expect_message(Status("idle", 0, 1))
        await r.kill(newer)
        r.ref.tell(Sensed(r.floor.ref, people(4.0)))
        await r.time.time_passes(1.0)
        await r.screens[1].expect_message(Enter(r.now()))
        await r.floor.expect_message(Status("idle", 1, 1))
        await r.floor.expect_message(Status("follow", 1, 1))


async def test_floor_gone_goes_idle() -> None:
    async with rig() as r:
        await r.follow()
        await r.kill(r.floor)
        await r.time.time_passes(3.0)
        for s in r.screens:
            await s.expect_message(Idle())
        again: TestProbe[Status] = r.testkit.create_test_probe()
        r.ref.tell(AttachFloor(again.ref))
        await again.expect_message(Status("idle", 0, 1))
