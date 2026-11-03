"""Ads as an interrupt: every screen plays the clip, then shows what the character would."""

from koi_signage.character import AD_LEAD_S
from koi_signage.messages import Ad, Cancel, Enter, Exit, Idle, PlayAd, Prepare, Ready, Status
from util import people, rig


async def test_ad_interrupts_follow_on_every_screen() -> None:
    async with rig() as r:
        await r.follow()
        r.ref.tell(Ad("sample.mp4", 10.0))
        t = r.now() + AD_LEAD_S
        for n in r.attached:
            await r.screens[n].expect_message(PlayAd("sample.mp4", t))
        await r.floor.expect_message(Status("ad", 1, 1))


async def test_ad_cancels_a_handoff_in_progress() -> None:
    async with rig() as r:
        await r.follow()
        r.ref.tell(people(3.2))
        await r.screens[0].expect_message(Prepare())
        r.ref.tell(Ad("sample.mp4", 10.0))
        await r.screens[0].expect_message(Cancel())
        for n in r.attached:
            await r.screens[n].expect_message(PlayAd("sample.mp4", r.now() + AD_LEAD_S))
        r.ref.tell(Ready(0))
        r.ref.tell(people(2.5))  # walked on to screen 0: no handoff while the ad plays
        await r.time.time_passes(2.0)
        for s in r.screens:
            await s.expect_no_message(0)


async def test_screens_hold_still_while_the_ad_plays() -> None:
    async with rig() as r:
        r.ref.tell(Ad("sample.mp4", 10.0))
        for n in r.attached:
            await r.screens[n].expect_message(PlayAd("sample.mp4", r.now() + AD_LEAD_S))
        await r.floor.expect_message(Status("ad", 0, 1))
        r.ref.tell(people(4.0))
        await r.floor.expect_message(Status("ad", 1, 1))
        await r.time.time_passes(1.0)  # long enough to follow: it does, but shows nothing
        for s in r.screens:
            await s.expect_no_message(0)


async def test_after_the_slot_the_screens_show_the_person_being_followed() -> None:
    async with rig() as r:
        await r.follow()
        r.ref.tell(Ad("sample.mp4", 10.0))
        for n in r.attached:
            await r.screens[n].expect_message(PlayAd("sample.mp4", r.now() + AD_LEAD_S))
        await r.time.time_passes(AD_LEAD_S + 9.9)
        for s in r.screens:
            await s.expect_no_message(0)
        await r.time.time_passes(0.1)
        t = r.now()
        for n in r.attached:
            await r.screens[n].expect_message(Enter(t) if n == 1 else Exit(t))
        await r.floor.expect_message(Status("ad", 1, 1))
        await r.floor.expect_message(Status("follow", 1, 1))


async def test_after_the_slot_with_nobody_there_the_screens_idle() -> None:
    async with rig() as r:
        r.ref.tell(Ad("sample.mp4", 5.0))
        for n in r.attached:
            await r.screens[n].expect_message(PlayAd("sample.mp4", r.now() + AD_LEAD_S))
        await r.time.time_passes(AD_LEAD_S + 5.0)
        for n in r.attached:
            await r.screens[n].expect_message(Idle())


async def test_a_new_ad_replaces_the_one_playing() -> None:
    async with rig() as r:
        r.ref.tell(Ad("a.mp4", 10.0))
        for n in r.attached:
            await r.screens[n].expect_message(PlayAd("a.mp4", r.now() + AD_LEAD_S))
        await r.time.time_passes(5.0)
        r.ref.tell(Ad("b.mp4", 10.0))
        for n in r.attached:
            await r.screens[n].expect_message(PlayAd("b.mp4", r.now() + AD_LEAD_S))
        await r.time.time_passes(AD_LEAD_S + 5.0)  # the first ad's slot is over: nothing
        for s in r.screens:
            await s.expect_no_message(0)
        await r.time.time_passes(5.0)
        for n in r.attached:
            await r.screens[n].expect_message(Idle())


async def test_a_screen_that_connects_mid_ad_joins_it() -> None:
    async with rig(attach=(0,)) as r:
        r.ref.tell(Ad("sample.mp4", 10.0))
        t = r.now() + AD_LEAD_S
        await r.screens[0].expect_message(PlayAd("sample.mp4", t))
        await r.time.time_passes(3.0)
        late = r.attach(1)
        await late.expect_message(PlayAd("sample.mp4", t))  # its start time: it seeks to catch up
