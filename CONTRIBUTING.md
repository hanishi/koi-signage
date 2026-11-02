# Contributing to koi-signage

koi-signage is people-reactive signage built on [ohra](https://github.com/hanishi/ohra) actors.
Read the [design](docs/design.md) first. Bug reports, fixes, docs and new koi are welcome. Before
you start anything large, open an issue so we can agree on the scope.

## Setup

```
uv sync --all-extras
```

## Checks

Every PR has to pass these checks, and CI runs them on Python 3.12 and 3.13:

```
uv run ruff format   # PEP 8 layout, lines up to 99 characters
uv run ruff check
uv run pyright       # strict mode, 0 errors
uv run pytest        # every test fails if any asyncio task outlives it (tests/conftest.py)
node --test tests/js/*.test.mjs  # the screens' clock-offset estimate
```

`ruff format` leaves comments, docstrings and strings alone, so wrap those yourself.

The server reads its static files (`src/koi_signage/static/`) once at startup. After changing a
page or `koi.js`, restart it to see the change.

## Writing tests

- **Nothing may outlive a test.** The autouse fixture in `tests/conftest.py` fails every test
  that leaves an asyncio task running. Start actors inside `async with ActorTestKit()`.
- **Wait on a condition, not a duration.**
  - Use `TestProbe` as screens, floors and the character.
  - Use `ManualTime` for every threshold: `tests/util.py`'s `rig()` gives you a character on
    the packaged `venue.toml`, on a manual clock, with probes attached.
- **Assert on messages.** Character decides everything, so most behaviour is "these frames in,
  these commands out". `follow_step` and `venue.py` are pure functions; test them directly.

## Rules

- **Use only ohra's public API.** If something is missing, the fix belongs in ohra, as a small PR
  there.
- **Behaviors are values.** Handlers return the next behavior. State lives in parameters (a
  frozen dataclass and `replace`), not in mutable fields.
- **Character is the only decision-maker.** Floor and Display relay; they never decide what a
  screen shows.
- **The sensor actor owns what the sensor would.** Floor stands in for the LD2450: anything the
  real radar filters (its field of view, its 3-target limit, its region filter) is filtered
  there, so swapping in the UART actor changes nothing downstream.
- **The realtime path makes no network or LLM calls.** Frames to commands stays on the venue
  machine.
- **The core depends on `ohra` only.** The pages use no build step and no JavaScript libraries.

## Style

- Python 3.12 generics syntax, frozen dataclasses for messages, and `match` for dispatch.
- Calibration values go in `venue.toml`, not in code: a real radar reads off and real people
  stand in odd places.

## Pull requests

- Keep each PR to one change, with tests that fail without it.
- Explain the why in the description.
- By contributing, you agree that your contribution is licensed under Apache-2.0, the license of
  this project.
