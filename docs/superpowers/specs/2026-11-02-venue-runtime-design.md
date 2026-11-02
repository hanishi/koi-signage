# Venue runtime (pointer sensor): design

Date: 2026-11-02. Source concept:
[人に反応するサイネージを、Raspberry Pi とミリ波レーダーで作る構想](https://note.com/programmer_llc/n/nc70f6eca15ee).

## Goal

The first piece of the venue software from the article, built before any hardware. The mouse
pointer on a web page stands in for the HLK-LD2450 radar. Everything after the sensor
(the character's idle/follow/crowd state and the screen-to-screen handoff) is the real code that
will later run on the Pi.

Success:

- On one laptop, moving the pointer over the floor makes the character follow it across three
  screens. Clicking drops people who stand still, which drives crowd mode.
- The 1 s and 3 s thresholds, the boundary dead zone and the handoff are tested on a manual
  clock, with no sleeps.
- Opening `/screen/N` on a real tablet works with no code change, so the article's sync and
  kiosk spike checks can run before the radar arrives.
- Replacing the pointer with the radar means replacing one actor that emits the same `Frame`.

## Out of scope for v1

| Left out | Add when |
|---|---|
| Uplink, Outbox, CreativeCache (Promovolve) | the HTTPS contract with Promovolve is agreed |
| Operator agent (ohra-agents) | it runs and the agent is still wanted |
| LD2450 UART sensor | the radar arrives |
| Follow cap (screens or seconds, the creepiness mitigation) | after a first walk-through |
| Walking-speed lead on the handoff time | latency is measured on tablets |
| Loop-lag metric | it runs on the Pi |
| Real creatives: the character is a placeholder glyph | Promovolve supplies assets |

## Stack

Python 3.12+, `ohra[web]>=0.5` (FastAPI, uvicorn, `actors.websocket`), and `tomllib` from the
stdlib. Dev: pytest, pytest-asyncio, pyright strict, ruff, httpx. The toolchain settings and the
leaked-task `conftest.py` are copied from ohra-agents. The front end is plain HTML and JS, with no
build step.

## Layout

```
signage/
  pyproject.toml
  venue.toml               # calibration: floor size, zone cuts, thresholds
  src/signage/
    venue.py               # Venue config: load from TOML, zone/screen lookup
    messages.py            # Frame, Target, and every message between actors
    character.py           # the state machine: the only actor that decides
    floor.py               # the floor page's connection actor: the simulated sensor
    display.py             # one screen's connection actor
    app.py                 # FastAPI, the guardian, routes
    static/index.html      # 3 screens + floor + status, one page
    static/screen.html     # one screen, ?n=0..2, for a tablet
  tests/
```

Tracking is a pure function in `venue.py`, not an actor: it holds no state yet. It becomes an
actor when smoothing needs memory.

## Venue config (`venue.toml`)

These are calibration knobs, set per site. A real radar reads off and real people stand in odd
places, so none of them is a constant in code.

```toml
[floor]
width_m = 9.0
depth_m = 4.0
zone_cuts_m = [1, 2, 3, 4, 5, 6, 7, 8]   # 9 zones along the corridor; 3 per screen, left to right

[character]
follow_after_s = 1.0    # 1 person this long → Follow
crowd_after_s = 1.0     # 2+ this long → Crowd
idle_after_s = 3.0      # 0 this long → Idle
crowd_lead_s = 1.0      # a screen must lead this long before the character moves toward it
linger_s = 3.0          # after arriving in crowd mode, stay at least this long
dead_zone_m = 0.3       # half-width of the band around a screen boundary
handoff_lead_s = 0.15   # exit/enter time t = now + this
ready_timeout_s = 1.0   # a screen that hasn't sent ready by then is handed off to anyway
```

Screen `s` covers zones `3s .. 3s+2`. The screen boundaries are the 3rd and 6th zone cuts.

## Actors and data flow

```
floor page ──ws──▶ Floor (sensor) ──Frame @10fps──▶ Character ──Prepare/Cancel/Enter/Exit/Idle──▶ Display n ──ws──▶ screen n
                       ▲                               │  ▲                                         │
                       └──────────Status───────────────┘  └───────────Attach / Ready────────────────┘
```

- **Guardian** (app.py) spawns Character, watches it, and answers `GetCharacter`. The routes ask
  it once per connection, as restock does with `Connect`. If Character has stopped, the guardian
  spawns a fresh one.
- **Floor** is the connection actor for `/ws/floor`. The page sends the current targets
  `{targets: [{x, y}, ...]}` whenever the pointer moves or a click adds or removes a person. The
  actor keeps the latest set and emits a `Frame` to Character on a 100 ms timer, whether or not
  anything moved, as the radar does. Input is clamped server-side: at most 3 targets, and points
  outside the floor are dropped. It sends `AttachFloor(self)` on start and forwards the `Status`
  it receives to the page.
- **Character** is the only decision-maker (next section). It watches every attached Display and
  the Floor.
- **Display n** is the connection actor for `/ws/screen/{n}`. On start it sends
  `AttachScreen(n, self)`. It relays commands to its tablet and the tablet's `ready` back as
  `Ready(n)`. It also answers clock pings from the page (see Handoff).

`actors.websocket` spawns connection actors under the root, not under the guardian. That is why
they register with Character instead of being its children.

Against the article's tree:

| Article | Here | Why |
|---|---|---|
| VenueActor | guardian | spawns, watches and respawns Character |
| SensorActor | Floor (connection actor) | the pointer arrives over a socket. The LD2450 actor will be a guardian child under `restart_with_backoff` |
| TrackingActor | pure functions in `venue.py` | no state yet. It becomes an actor when smoothing or standing-person memory needs state |
| CharacterActor | Character, a guardian child | |
| DisplayActor ×3 | Display (connection actors) | each lives exactly as long as its tablet's socket |
| UplinkActor | not in v1 | arrives with the Promovolve contract, as a guardian child with a persisted Outbox |

## Character

State: `mode ∈ {Idle, Follow, Crowd}`, `screen` (0..2, starting at 1, the middle), the attached
displays, and handoff and timer bookkeeping. Every rule below runs on ohra timers, so ManualTime drives it in tests.

**Mode switching.** For each `Frame`, `seen = min(count, 2)` (0, 1, or 2+). If `seen` would mean
a different mode, a single timer `Settle(seen)` starts with that mode's threshold. A different
`seen` restarts it with its own threshold. A `seen` that matches the current mode cancels it.
When `Settle` fires, the mode changes and the character stays on its current screen. Entering
Idle shows the attract loop on every screen. Leaving Idle shows the character on `screen`.

**Follow.** There is exactly one target, so the radar's track-ID swaps don't matter. Let `b` be
the screen boundary nearest the target, toward screen `s'`:

- The target enters the band `[b − dead_zone, b + dead_zone]`: `Prepare` goes to `s'`.
- The target leaves the band on the far side: hand off to `s'`.
- The target leaves the band on the near side: `Cancel` goes to `s'`.
- The target is outside every band and on a screen other than `screen` (just after a mode
  change): hand off one screen toward it, then apply these rules again.

**Crowd.** Per-screen counts are the sums of their zones. A screen with strictly more people than
every other is the leader. If it is not the current screen and has led for `crowd_lead_s`, and
the character has spent `linger_s` on its current screen, the character moves **one** screen
toward it. A tie means no leader, so the character stays.

**Handoff** from `s` to `s'`. The character sends `Prepare` to `s'` if it hasn't yet, and waits
for `Ready(s')`, or for `ready_timeout_s`, whichever comes first. Then, with `t = clock() + handoff_lead_s`, it sends `Exit(t)` to `s` and
`Enter(t)` to `s'`. `clock` is a parameter (default `time.monotonic`, so NTP steps can't move it),
which keeps it testable. If `s'` has no display attached, the character moves anyway and the
`Enter` is dropped.

**Attach and DeathWatch.** On `AttachScreen(n, ref)` the character watches `ref`, replacing an
older ref for `n` (the last tablet wins), and sends that screen the current state. A `Terminated`
display is removed, so the character skips sending to that screen. If the Floor terminates, the
character treats it as an empty frame, so it falls to Idle after `idle_after_s` and the screens
keep playing.

After any change, the character sends `Status(mode, count, screen)` to the Floor.

## Browser side

- **Clock offset.** Each screen page sends `ping{c}` five times at startup and then every 10 s.
  Display replies `pong{c, s}` with `s = time.monotonic()`. The page keeps the sample with the
  smallest RTT: `offset = s − (c + rtt/2)`, using `performance.now()/1000`. It runs `enter(t)` and
  `exit(t)` at local time `t − offset`.
- **index.html** opens four sockets (the floor plus three screens) and lays them out as in the
  mockup. **screen.html** opens one. Both use the same JS for a screen.
- Commands to a screen: `idle`, `prepare`, `cancel`, `enter{t}`, `exit{t}`. From a screen:
  `ready`, `ping{c}`.

## Errors

- A bad frame from a page: `decode` raises, `actors.websocket` closes with 1003, and the page
  reconnects.
- A Character crash: it stops instead of restarting. A restart would keep the same ref, so no page
  would reconnect, and the restarted Character would have no screens. Every connection actor
  watches Character, so they stop and close their sockets. The pages reconnect, and the guardian
  spawns a fresh Character for them.
- A tablet drop: DeathWatch (above). Its page reconnects with backoff.

## Testing

On ManualTime with `ActorTestKit`, with probes standing in for displays and the floor:

- 1 person for 1 s → Follow. 1 person for 0.5 s, then 0 → still Idle.
- 2+ for 1 s → Crowd. 0 for 3 s → Idle. 0 for 2.9 s, then 1 → no Idle.
- Follow: entering the band sends Prepare, turning back sends Cancel, and crossing sends Exit(t)
  and Enter(t) with the same `t`.
- Crowd: a tie stays, a 1 s lead moves one screen, and linger blocks a second move.
- A display stopped → no more messages to it. Re-attach → it gets the current state.
- Floor: more than 3 targets are capped, off-floor points are dropped, and a frame goes out every
  100 ms with no input.
- `venue.toml` loads, and zone/screen lookup is right at the cuts.
- One app smoke test: the floor and a screen socket connect through the TestClient, and the
  screen gets `idle`.
