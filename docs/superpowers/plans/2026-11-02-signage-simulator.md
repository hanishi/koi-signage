# Signage Simulator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The venue software from the signage article, with the mouse pointer on a web page in
place of the LD2450 radar: a character that idles, follows one person, or moves toward a crowd
across three screens.

**Architecture:** ohra actors. Floor (the simulated sensor) emits `Frame`s at 10 fps to
Character, the only decision-maker. Character drives three Display connection actors over
WebSockets. Tracking is a set of pure functions in `venue.py`. Every threshold runs on ohra timers,
so ManualTime tests it.

**Tech Stack:** Python 3.12+, `ohra[web]>=0.5` (FastAPI, uvicorn, `Actors.websocket`), `tomllib`.
Dev: pytest, pytest-asyncio, pyright strict, ruff, httpx. Plain HTML and JS.

**Spec:** `docs/superpowers/specs/2026-11-02-signage-simulator-design.md`

## Global Constraints

- Runtime dependency: `ohra[web]>=0.5` only. Use only ohra's public API: no `ohra.cell` imports
  and no `_private` names.
- Toolchain copied from `~/ohra-agents/pyproject.toml`:
  - ruff with line length 99 and `select = ["E", "W", "N"]`
  - pyright strict on `src` and `tests`
  - pytest with `asyncio_mode = "auto"`
  - the leaked-task `tests/conftest.py`, copied verbatim
- Behaviors are values. State lives in parameters (a frozen dataclass plus `dataclasses.replace`),
  never in mutable fields.
- Frozen dataclasses for messages, `match` for dispatch, and PEP 695 generics.
- Tests wait on conditions, never on durations: `ActorTestKit(manual_time=True)`, `ManualTime`,
  and `TestProbe`.
- `clock` defaults to `time.monotonic` everywhere it's a parameter. Character and Display must
  share one clock.
- Checks before every commit: `uv run ruff format && uv run ruff check && uv run pyright && uv run pytest`.

## Review Focus

1. **A screen page that never answers `ready`** (crashed JS, slow tablet). The character must
   still move after `ready_timeout_s`. Owned by Task 3: `test_handoff_without_ready_times_out`.
2. **A pointer jittering on a screen boundary.** One `Prepare` per band entry, no repeated
   `Prepare` or `Cancel` while inside the band, and at most one handoff per crossing. Owned by
   Task 3: `test_jitter_inside_band_sends_one_prepare`.
3. **Malformed floor input:** non-JSON, `NaN` (which Python's `json` accepts), strings, bools as
   numbers, 100 targets. Bad input must close the socket with 1003 or be clamped, and must never
   reach Character as a bad `Frame`. Owned by Task 5: `test_decode_floor_rejects` and
   `test_clamp`.
4. **Two tablets claiming the same screen.** The last one wins, and when the *older* one
   disconnects, the newer one must stay attached. Owned by Task 2:
   `test_stale_screen_gone_keeps_newer`. The same rule applies to two floor pages.
5. **The floor page closing mid-follow.** Idle after `idle_after_s`, and a reconnected floor
   resumes. Owned by Task 2: `test_floor_gone_goes_idle`.

---

### Task 1: Project scaffold and venue config

**Files:**
- Create: `pyproject.toml`, `venue.toml`, `.gitignore`, `src/signage/__init__.py`, `src/signage/py.typed`, `src/signage/venue.py`, `tests/conftest.py`
- Test: `tests/test_venue.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Venue` with fields:
    - `width_m: float`, `depth_m: float`
    - `zone_cuts_m: tuple[float, ...]`
    - `follow_after_s`, `crowd_after_s`, `idle_after_s`, `crowd_lead_s`, `linger_s`,
      `dead_zone_m`, `handoff_lead_s`, `ready_timeout_s`, all `float`
  - `load_venue(path: Path) -> Venue`
  - `zone_of(v: Venue, x: float) -> int`, which is 0..8 and uses `bisect_right`, so a point on a
    cut belongs to the zone on its right
  - `screen_of(v: Venue, x: float) -> int`, which is `zone_of // 3`
  - `boundaries(v: Venue) -> tuple[float, float]`, which is `(cuts[2], cuts[5])`
  - `screen_counts(v: Venue, targets: Sequence[Target]) -> tuple[int, int, int]`
- `Target` is defined here as `@dataclass(frozen=True) class Target: x: float; y: float`, and
  Task 2 re-exports it from `messages.py`.

- [ ] **Step 1: Scaffold.**
  - `pyproject.toml`:
    - name `signage`, `requires-python = ">=3.12"`
    - `dependencies = ["ohra[web]>=0.5"]`
    - `dev` extra: `pytest>=8`, `pytest-asyncio>=0.24`, `pyright>=1.1.380`, `ruff>=0.17`,
      `httpx>=0.27`
    - tool sections as in ohra-agents, with `pyright.include = ["src", "tests"]`
  - `venue.toml`: exactly the spec's block, including `ready_timeout_s = 1.0`.
  - `.gitignore`: `.venv/`, `__pycache__/`.
  - Copy `~/ohra-agents/tests/conftest.py`.
  - Run `uv sync --all-extras`.
- [ ] **Step 2: Write failing tests** in `tests/test_venue.py`:

```python
V = load_venue(Path(__file__).parent.parent / "venue.toml")

def test_loads_repo_venue():
    assert V.zone_cuts_m == (1, 2, 3, 4, 5, 6, 7, 8) and V.ready_timeout_s == 1.0

def test_zone_and_screen_at_cuts():
    assert [zone_of(V, x) for x in (0.0, 0.99, 1.0, 8.0, 9.0)] == [0, 0, 1, 8, 8]
    assert [screen_of(V, x) for x in (2.99, 3.0, 5.99, 6.0)] == [0, 1, 1, 2]
    assert boundaries(V) == (3, 6)

def test_screen_counts():
    assert screen_counts(V, [Target(0.5, 1), Target(4, 1), Target(4.5, 2)]) == (1, 2, 0)

def test_rejects_bad_cuts(tmp_path):  # write a toml with cuts [1, 3, 2, ...]; also only 7 cuts
    with pytest.raises(ValueError): load_venue(bad)
```

- [ ] **Step 3: Run** `uv run pytest tests/test_venue.py`. Expected: FAIL (import error).
- [ ] **Step 4: Implement `venue.py`.** `load_venue` uses `tomllib`. It raises `ValueError`
  unless there are exactly 8 strictly increasing cuts, all inside `(0, width_m)`.
- [ ] **Step 5: Run all checks.** Expected: PASS, 0 pyright errors.
- [ ] **Step 6: Commit** with the message `venue config: floor, zone cuts, thresholds; tracking as pure functions`.

### Task 2: Character: mode switching, attach, DeathWatch, status

**Files:**
- Create: `src/signage/messages.py`, `src/signage/character.py`
- Test: `tests/test_character_modes.py`

**Interfaces:**
- Consumes: Task 1's `Venue`, `Target`, and lookups.
- Produces, in `messages.py`:
  - `Frame(targets: tuple[Target, ...])`
  - Screen commands `Idle()`, `Prepare()`, `Cancel()`, `Enter(t: float)`, `Exit(t: float)`, and
    `type ScreenCmd = Idle | Prepare | Cancel | Enter | Exit`
  - `AttachScreen(n: int, ref: ActorRef[ScreenCmd])`, `Ready(n: int)`
  - `AttachFloor(ref: ActorRef[Status])`
  - `Status(mode: Mode, count: int, screen: int)`, where `type Mode = Literal["idle", "follow", "crowd"]`
- Produces, in `character.py`:
  - `type CharacterMsg = Frame | AttachScreen | Ready | AttachFloor | <its private timer and watch messages>`.
    It's defined in `character.py`, not `messages.py`, to avoid a cycle. Floor and Display import
    it from there.
  - `character(venue: Venue, clock: Callable[[], float] = time.monotonic) -> Behavior[CharacterMsg]`

Decisions:
- The state is one frozen dataclass:
  - `mode`, `screen = 1`
  - `screens: Mapping[int, ActorRef[ScreenCmd]]`, `floor: ActorRef[Status] | None`
  - `settling: int | None` (the `seen` the settle timer is for)
  - `last_status: Status | None`
  - Tasks 3 and 4 add their own fields.
- Watches use `ctx.watch_with(ref, ScreenGone(n, ref))` and `ctx.watch_with(ref, FloorGone(ref))`.
  A `Gone` whose ref isn't the current one is ignored (Review Focus 4).
- Entering Idle: `Idle()` to every screen. Leaving Idle: `Enter(clock())` to `screen` and
  `Exit(clock())` to the others.
- On attach, the screen gets the current state: `Idle()`; or `Enter(clock())` if it's the
  character's screen; or `Exit(clock())` otherwise.
- `Status` goes to the floor only when `(mode, count, screen)` differs from `last_status`.
- `FloorGone` from the current floor sets `floor = None` and is handled as `Frame(())`.

- [ ] **Step 1: Write failing tests.**
  - Use `ActorTestKit(manual_time=True)`, `time = ManualTime(testkit.system)`, and
    `clock=lambda: time.scheduler.current_time`.
  - Probes stand in for screens (`TestProbe[ScreenCmd]`) and the floor (`TestProbe[Status]`).
  - The helper `people(*xs)` returns `Frame(tuple(Target(x, 1.0) for x in xs))`.
  - Tests:
    - `test_one_person_for_1s_follows`: after `people(4.0)` and `time_passes(1.0)`, screen 1
      gets `Enter(t)`, screens 0 and 2 get `Exit(t)`, and the floor gets
      `Status("follow", 1, 1)`.
    - `test_flicker_stays_idle`: `people(4.0)`, then `time_passes(0.5)`, then `people()`, then
      `time_passes(1.0)`. No `Enter` anywhere.
    - `test_two_for_1s_crowd`: `people(4, 4.5)`, then `time_passes(1.0)`. The floor gets
      `Status("crowd", 2, 1)`.
    - `test_zero_for_3s_idles`: from Follow, `people()` then `time_passes(3.0)`, and every
      screen gets `Idle()`. Separately, 2.9 s of empty frames and then `people(4)` gives no
      `Idle()`.
    - `test_attach_gets_current_state`: a screen attached while in Follow on screen 1 gets
      `Enter`. Attached to screen 0, it gets `Exit`. Attached in Idle, it gets `Idle()`.
    - `test_stopped_screen_gets_nothing`: stop the probe's ref. A later mode change sends
      nothing to it, and nothing else fails.
    - `test_stale_screen_gone_keeps_newer`: attach A to screen 0, then attach B to screen 0,
      then stop A. A mode change still reaches B.
    - `test_floor_gone_goes_idle`: in Follow, stop the floor, then `time_passes(3.0)`, and the
      screens get `Idle()`. A new floor attached gets `Status` on the next change.
- [ ] **Step 2: Run.** Expected: FAIL (import error).
- [ ] **Step 3: Implement** `messages.py` and the mode logic of `character.py`.
  - Use `Behaviors.with_timers`, one `start_single_timer("settle", Settle(seen), threshold)`,
    and `cancel("settle")` when `seen` matches the current mode.
  - A changed `seen` restarts the timer.
- [ ] **Step 4: Run all checks.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `character: idle/follow/crowd with debounced switching, screens and floor attach under DeathWatch`.

### Task 3: Character: follow and handoff

**Files:**
- Modify: `src/signage/character.py`
- Test: `tests/test_character_follow.py`

**Interfaces:**
- Produces: `follow_step(v: Venue, screen: int, x: float) -> tuple[Literal["stay", "prepare", "handoff"], int]`,
  a pure function in `character.py`. Task 4 reuses the handoff path.

The algorithm `follow_step` encodes (the signature leaves it open):

```
for n in (screen - 1, screen + 1) that exist:
    b = the boundary between screen and n
    d = (x - b) if n > screen else (b - x)      # > 0 means on n's side
    if d > dead_zone:  return ("handoff", n)
    if d >= -dead_zone: return ("prepare", n)
return ("stay", screen)
```

A far-away target produces `handoff` one screen at a time, which covers the spec's "after a
mode change" rule.

New state fields:
- `prepared: int | None`
- `ready: int | None` (a `Ready` that arrived for `prepared`)
- `moving: int | None` (a handoff waiting for Ready)

Rules:
- Only in Follow with `count == 1`, and not while `moving`.
- `stay` with `prepared` set: send `Cancel()` and clear it.
- `prepare n` with `prepared != n`: send `Cancel` to the old one if any, send `Prepare()` to
  `n`, and set `prepared = n`.
- `handoff n`:
  - If `ready == n`, or `n` isn't attached, complete at once.
  - Otherwise send `Prepare` if it isn't already prepared, set `moving = n`, and start
    `start_single_timer("ready", ReadyTimeout(n), ready_timeout_s)`.
- `Ready(n)` completes when `moving == n`, and records `ready = n` when `prepared == n`.
  `ReadyTimeout(n)` completes when `moving == n`.
- Completing:
  - `t = clock() + handoff_lead_s`
  - `Exit(t)` to the old screen and `Enter(t)` to the new one
  - `screen = n`, then clear `prepared`, `ready` and `moving`, and cancel `"ready"`
  - start `start_single_timer("linger", LingerDone(), linger_s)`, which Task 4 uses
  - send `Status`
- Any mode change clears the handoff state: `Cancel` to `prepared`, and cancel the `"ready"`
  timer.

- [ ] **Step 1: Write failing tests.**
  - `test_follow_step` is a table on the repo venue (boundaries 3 and 6, dead zone 0.3):

```python
assert follow_step(V, 1, 4.5) == ("stay", 1)
assert follow_step(V, 1, 3.2) == ("prepare", 0)
assert follow_step(V, 1, 2.8) == ("prepare", 0)
assert follow_step(V, 1, 2.6) == ("handoff", 0)
assert follow_step(V, 1, 6.31) == ("handoff", 2)
assert follow_step(V, 0, 8.0) == ("handoff", 1)
```

  - Actor tests, in Follow on screen 1 with all three screens attached:
    - `test_band_prepare_then_turn_back_cancels`: `people(3.2)` sends `Prepare()` to screen 0,
      and `people(4.5)` then sends `Cancel()`.
    - `test_crossing_hands_off_with_same_t`: `people(3.2)`, then screen 0 replies
      `Ready(0)`, then `people(2.5)`. Screen 1 gets `Exit(t1)` and screen 0 gets `Enter(t0)`,
      with `t0 == t1 == now + 0.15`.
    - `test_handoff_without_ready_times_out`: `people(2.5)` with no Ready, then
      `time_passes(1.0)`. `Exit` and `Enter` both arrive.
    - `test_jitter_inside_band_sends_one_prepare`: frames at 3.2, 2.9, 3.1, 2.8 send exactly
      one `Prepare()` to screen 0, and no `Cancel`, `Exit` or `Enter`.
    - `test_far_target_steps_one_screen`: on screen 0, `people(8.0)` gives one handoff to 1 and
      then one to 2. Each waits for Ready or the timeout.
    - `test_handoff_to_detached_screen_moves`: screen 0 not attached and `people(2.5)`. Screen 1
      gets `Exit` at once, and `Status` reports screen 0.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** `follow_step` and the handoff path.
- [ ] **Step 4: Run all checks.** Expected: PASS, and Task 2's tests are still green.
- [ ] **Step 5: Commit** with the message `character: follow mode with boundary dead zone, Prepare/Ready/Cancel and a synchronised Exit/Enter handoff`.

### Task 4: Character: crowd

**Files:**
- Modify: `src/signage/character.py`
- Test: `tests/test_character_crowd.py`

**Interfaces:**
- Consumes: Task 3's handoff path and the `"linger"` timer, and Task 1's `screen_counts`.

Rules (Crowd mode only):
- `leader` is the index of the strictly largest count in `screen_counts`, or `None` on a tie.
- Leader `None`, or equal to `screen`: cancel `"lead"` and clear `lead` and `lead_due`.
- Otherwise, if `lead != leader`: `start_single_timer("lead", LeadDone(leader), crowd_lead_s)`,
  set `lead = leader`, and set `lead_due = False`.
- `LeadDone(l)` with `l == lead` sets `lead_due = True`, then calls `try_move`. `LingerDone()`
  also calls `try_move`.
- `try_move`: if Crowd, `lead_due`, `"linger"` not active, and not `moving`, hand off to
  `screen + sign(lead - screen)`, then clear `lead` and `lead_due`. The next frame re-arms the
  lead timer if the leader is still elsewhere.

- [ ] **Step 1: Write failing tests.** Enter Crowd on screen 1 first, with all screens attached
  and every Ready answered by the test.
  - `test_tie_stays`: `people(0.5, 8.5)` for 5 s gives no `Exit` or `Enter`.
  - `test_lead_for_1s_moves_one_screen`: `people(8.0, 8.5)` (screen 2 leads), then
    `time_passes(1.0)`. The character hands off 1→2.
  - `test_linger_blocks_second_move`: arrive on screen 2, then `people(0.5, 1.0, 1.5)` (screen
    0 leads). No move before 3 s since arrival. After 3 s it moves to 1, and only to 1.
  - `test_leader_change_restarts_lead`: screen 2 leads for 0.6 s, then screen 0 leads for 0.6 s.
    No move yet.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all checks.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `character: crowd mode moves one screen toward a sustained leader, lingers after arriving, stays on a tie`.

### Task 5: Floor, the simulated sensor

**Files:**
- Create: `src/signage/floor.py`
- Test: `tests/test_floor.py`

**Interfaces:**
- Consumes: `Frame`, `Target`, `AttachFloor`, `Status`, and `Venue`.
- Produces:
  - `Pointer(targets: tuple[Target, ...])`
  - `decode_floor(text: str) -> Pointer`. It raises `ValueError` for anything other than
    `{"targets": [{"x": n, "y": n}, ...]}` with finite, non-bool numbers.
  - `clamp(v: Venue, targets: Sequence[Target]) -> tuple[Target, ...]`. It drops points outside
    `[0, width] × [0, depth]` and then keeps the first 3.
  - `floor(venue: Venue, character: ActorRef[CharacterMsg], out: ActorRef[dict[str, object]]) -> Behavior[FloorMsg]`,
    where `FloorMsg = Pointer | Status | _Tick | _CharacterGone`.

Behavior:
- On setup: tell `AttachFloor(ctx.self)`, call `ctx.watch_with(character, _CharacterGone())`, and
  start `start_timer_with_fixed_delay("tick", _Tick(), 0.1)`.
- `Pointer` replaces the latest targets with `clamp(...)`.
- `_Tick` tells `Frame(latest)`.
- `Status` tells `out` `{"type": "status", "mode": ..., "count": ..., "screen": ...}`.
- `_CharacterGone` returns `Behaviors.stopped()`, which closes the socket.

- [ ] **Step 1: Write failing tests.**
  - `test_decode_floor_rejects`, parametrized over each of these raising `ValueError`:
    - `"not json"`
    - `'{"targets": [{"x": NaN, "y": 1}]}'`
    - `'{"targets": [{"x": "1", "y": 1}]}'`
    - `'{"targets": [{"x": true, "y": 1}]}'`
    - `'{"targets": 3}'`
    - `'[]'`
  - `test_clamp`: 5 in-floor points keep the first 3, and `Target(-0.1, 1)` and
    `Target(1, 4.1)` are dropped.
  - `test_frames_every_100ms_without_input`: the character is a probe. After the
    `AttachFloor`, `time_passes(0.3)` gives exactly 3 `Frame(())`.
  - `test_pointer_then_frame`: tell `Pointer((Target(4, 1),))`, then `time_passes(0.1)`. The
    probe gets `Frame((Target(4, 1),))`.
  - `test_status_forwarded`: tell `Status("follow", 1, 1)`. The `out` probe gets the dict above.
  - `test_stops_when_character_stops`: stop the character probe, and the floor terminates.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Reject non-finite numbers with `math.isfinite`, and bools with an
  explicit `isinstance(v, bool)` check before `int | float`.
- [ ] **Step 4: Run all checks.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `floor: the pointer as a simulated radar, clamped to 3 targets on the floor, a frame every 100 ms`.

### Task 6: Display, one screen's connection actor

**Files:**
- Create: `src/signage/display.py`
- Test: `tests/test_display.py`

**Interfaces:**
- Consumes: `ScreenCmd`, `AttachScreen`, `Ready`, and `CharacterMsg`.
- Produces:
  - `PageReady()`, `Ping(c: float)`
  - `decode_screen(text: str) -> PageReady | Ping`, which accepts `{"type": "ready"}` and
    `{"type": "ping", "c": finite}`, and raises `ValueError` otherwise
  - `display(n: int, character: ActorRef[CharacterMsg], out: ActorRef[dict[str, object]], clock: Callable[[], float] = time.monotonic) -> Behavior[DisplayMsg]`,
    where `DisplayMsg = ScreenCmd | PageReady | Ping | _CharacterGone`

Behavior:
- On setup: tell `AttachScreen(n, ctx.self)` and call `ctx.watch_with(character, _CharacterGone())`.
- Commands go to `out` as `{"type": "idle" | "prepare" | "cancel"}` or
  `{"type": "enter" | "exit", "t": t}`.
- `PageReady` tells `Ready(n)`.
- `Ping(c)` tells `out` `{"type": "pong", "c": c, "s": clock()}`.
- `_CharacterGone` returns `Behaviors.stopped()`.

- [ ] **Step 1: Write failing tests.**
  - `test_attaches_on_start`
  - `test_commands_to_json`, which checks `Enter(2.5)` becomes `{"type": "enter", "t": 2.5}`
    and checks `Idle()` too
  - `test_ready_relayed_as_Ready_n`
  - `test_pong_uses_clock`, with a fixed `clock=lambda: 42.0`, so `Ping(1.5)` gives
    `{"type": "pong", "c": 1.5, "s": 42.0}`
  - `test_decode_screen_rejects`, for `'{"type": "ping", "c": NaN}'` and `'{"type": "x"}'`
  - `test_stops_when_character_stops`
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all checks.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `display: one screen's connection actor, commands as JSON, ready relayed, clock pings answered`.

### Task 7: App, guardian, pages

**Files:**
- Create: `src/signage/app.py`, `src/signage/static/index.html`, `src/signage/static/screen.html`, `src/signage/static/screen.js`
- Modify: `pyproject.toml` (package data for `static/*`)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `GetCharacter(reply_to: ActorRef[ActorRef[CharacterMsg]])`
  - `guardian(venue: Venue) -> Behavior[GetCharacter | _CharacterStopped]`. It spawns
    `character(venue)` as `character-<k>`, watches it, and spawns a fresh one with `k + 1` on
    the first `GetCharacter` after it stops.
  - `create_app(venue: Venue) -> FastAPI`
  - `from_env() -> FastAPI`, which reads `VENUE` (default `venue.toml`)

Routes:
- `GET /` serves `index.html`, and `GET /screen` serves `screen.html`.
- `GET /static/screen.js`
- `WS /ws/floor` runs `actors.websocket(ws, lambda out: floor(venue, ch, out), decode_floor)`.
- `WS /ws/screen/{n}`, with `n: Annotated[int, Path(ge=0, le=2)]`, runs `display(n, ch, out)`.
- Every route gets `ch` from `await system.ask(GetCharacter, timeout=2)`.
- `FastAPI(lifespan=actors.lifespan, exception_handlers=actors.exception_handlers)`, as in restock.

Pages: no framework, keep them small.
- `screen.js` exports `connectScreen(n, el)`:
  - It runs the clock-offset pings: 5 at start, then every 10 s, keeping the sample with the
    minimum RTT.
  - It renders `idle` as an attract loop, `exit` as blank, and `enter` as the character glyph,
    with enter and exit scheduled at `t − offset`. `prepare` replies `ready`.
  - It reconnects with backoff: 0.5 s doubling to 8 s.
- `index.html` lays out three screens above the floor plus a status line:
  - `mousemove` over the floor sets the pointer target.
  - `mouseleave` removes the pointer target.
  - A click toggles a standing person. The page caps at 3, matching the server.
  - The page sends `{targets}` on every change.
  - The status line shows the floor socket's `status` frames.
- `screen.html?n=N` gives one screen, full-window.

- [ ] **Step 1: Write failing tests** in `tests/test_app.py`, using `TestClient(create_app(load_venue(...)))`:
  - `test_screen_gets_idle_on_connect`: `/ws/screen/0` receives `{"type": "idle"}`.
  - `test_floor_and_screen_follow`:
    - Connect floor and screen 1.
    - Send `{"targets": [{"x": 4, "y": 1}]}`.
    - Within real time (the app runs a real clock), screen 1 receives `enter` and the floor
      receives `status` with `mode == "follow"`.
    - Read frames with a loop bounded by count, not by sleeping.
  - `test_bad_screen_index_rejected`: `/ws/screen/3` fails to connect.
  - `test_bad_floor_frame_closes_1003`: `"nope"` closes the socket with code 1003.
  - `test_guardian_respawns_character`: in an `ActorTestKit`, `GetCharacter`, stop the returned
    ref, wait with `probe.expect_terminated`, and `GetCharacter` again gives a different, live
    ref.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** `app.py` and the three static files.
- [ ] **Step 4: Run all checks.** Expected: PASS.
- [ ] **Step 5: Manual check.**
  - Run `uv run uvicorn --factory signage.app:from_env --port 8124` and open
    http://localhost:8124/.
  - The pointer held over the floor for 1 s brings the character, which follows across screens.
  - Two clicks give `crowd` in the status line.
  - Moving off the floor gives the attract loop on all three screens after 3 s.
  - `http://localhost:8124/screen?n=2` in a second window mirrors screen 2.
- [ ] **Step 6: Commit** with the message `app: guardian, floor and screen WebSockets, the one-page simulator and a per-tablet screen page`.
- [ ] **Step 7: Add a README.** Write a short one: what this is (link the article), the run
  command, `venue.toml` as calibration, and v1's out-of-scope table from the spec. Commit it.
