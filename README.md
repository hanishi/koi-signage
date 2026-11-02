# signage

The venue runtime for people-reactive signage, on [ohra](https://github.com/hanishi/ohra). It is
the Raspberry Pi side of
[人に反応するサイネージを、Raspberry Pi とミリ波レーダーで作る構想](https://note.com/programmer_llc/n/nc70f6eca15ee).

A character plays across three screens:
- With nobody there, it idles.
- With one person, it follows them from screen to screen.
- With several, it moves toward the busiest screen.

Until the HLK-LD2450 radar is here, the mouse pointer on a web page stands in for it. Everything
after the sensor is the real code:
- the character's state machine
- the screen-to-screen handoff
- the tablets' clock sync

## Run

```
uv sync --all-extras
uv run uvicorn --factory signage.app:from_env --host 0.0.0.0 --port 8124
```

- **http://localhost:8124/** shows the three screens above the floor.
  - Move the pointer over the floor to walk in.
  - Click to leave someone standing.
  - Move off the floor to leave.
- **http://&lt;pi&gt;:8124/screen?n=0** (and `1`, `2`) is one screen, full-window, for a tablet's
  kiosk browser.

`--host 0.0.0.0` lets tablets on the LAN connect. Use `127.0.0.1` to keep it on this machine.

## Actors

| Actor | Does |
|---|---|
| guardian | spawns Character, and a fresh one if it stops |
| Floor (one per floor page) | the pointer as the radar: a `Frame` every 100 ms, at most 3 people |
| Character | idle / follow / crowd, and which screen shows the character. The only one that decides |
| Display (one per screen socket) | commands to its tablet, the tablet's ready back, and clock pings |

The LD2450 actor will replace Floor and send the same `Frame`. The
[design](docs/superpowers/specs/2026-11-02-venue-runtime-design.md) maps this tree against the
article's.

## Calibration

`venue.toml` holds the floor size, the zone cuts (3 zones per screen) and every threshold. They
are set per site, because a real radar reads off and real people stand in odd places. `$VENUE`
points at another file.

## Not yet

| Left out | Add when |
|---|---|
| Uplink, Outbox, CreativeCache (Promovolve) | the HTTPS contract with Promovolve is agreed |
| Operator agent (ohra-agents) | this runs and the agent is still wanted |
| LD2450 UART sensor | the radar arrives |
| Follow cap (the creepiness mitigation) | after a first walk-through |
| Walking-speed lead on the handoff time | latency is measured on tablets |
| Loop-lag metric | it runs on the Pi |
| Real creatives: the character is a placeholder glyph | Promovolve supplies assets |

## Checks

```
uv run ruff format && uv run ruff check && uv run pyright && uv run pytest
```
