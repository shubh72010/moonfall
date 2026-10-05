# moonfall

Shoot-and-dodge arcade game built on a zero-dependency 2D paint engine
(pure Python stdlib + tkinter). 480×270 pixel frames rendered with C-level
fills, zoomed fullscreen at ~25fps.

## Run

```
python3 game.py          # needs Python 3.10+ and tkinter
python3 game.py --selftest
```

## Controls

| Key | Action |
|---|---|
| ← → / A D | ride the hill |
| K / X | shoot (kills = coins) |
| Space | jump (clears ground walkers) |
| B | shop |
| 1–5 | buy upgrades in the shop |
| P / R / Q | pause / restart / quit |
| F11 | fullscreen |

Survive the wave — every 20s (then every 30s) the shop opens. Spend kill
coins on **rapid fire**, **twin shot**, **extra heart**, **swift boots**,
**ring magnet**. Falling moons: strafe or shoot. Comets: fast and diagonal.
Walkers: jump or shoot. Rings build a combo (×5 max) — chain them before
the 4s timer drops it.

## Engine

`engine.py` is the shared paint library: `sky/hill/disc/ring/line/fade`
ops over a raw RGB buffer, PNG writer, caption filters, ffmpeg mux. The
game uses only the paint ops; the mux path is for films (`python3
engine.py` runs its selftest).
