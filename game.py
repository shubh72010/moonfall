#!/usr/bin/env python3
"""moonfall: shoot-and-dodge game on the 2d paint engine. zero deps (tkinter).

run: python3 game.py  (arrows/A-D ride the hill, K/X shoot the falling
moons, Space jump the rolling walkers, grab rings for a combo, B shop,
P pause, R restart, Q quit, F11 fullscreen).
Wave 1 lasts 20s, later waves 30s, then the shop opens: spend kill coins on
twin shot, extra hearts, swift boots, ring magnet. reuses engine.py paint ops
at native 480x270 zoomed to the screen; ~25fps pooled, step() is pure and
headless-testable.
"""
import math
import os
import random
import sys
import tempfile
import time

import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as e

W, H = e.W, e.H
TICK_MS = 40
PR = 8.0                      # player radius
ACC, MAXV, DRAG = 900.0, 260.0, 6.0
G, JUMP = 900.0, 360.0        # gravity and takeoff speed (apex ~72px)
INV, TRAILN = 1.5, 8          # i-frames after a hit, trail length
FIRE0, SHOT_V = 0.28, 320.0   # base shot cooldown and muzzle speed
B = {"m": 4, "c": 8, "w": 12}  # coin bounty per enemy kind
SHOP = [                       # k, name, max level, base cost (scales x level)
    {"k": "rapid", "n": "rapid fire", "max": 3, "cost": 25},
    {"k": "twin", "n": "twin shot", "max": 2, "cost": 45},
    {"k": "heart", "n": "extra heart", "max": 3, "cost": 40},
    {"k": "speed", "n": "swift boots", "max": 3, "cost": 30},
    {"k": "magnet", "n": "ring magnet", "max": 3, "cost": 35},
]
FG = (H - 35, 12.0, 0.045, 4.0)   # foreground hill: base, amp, freq, phase
BG = (H - 70, 22.0, 0.03, 1.0)

SKY = e.sky([(0.0, (6, 6, 20)), (0.55, (36, 18, 56)), (1.0, (14, 8, 24))])
_rng = random.Random(7)
STARS = [(_rng.randrange(W), _rng.randrange(H - 90), _rng.choice((1, 1, 2)))
         for _ in range(46)]
TMP = os.path.join(tempfile.mkdtemp(), "g.png")


def ground(x):
    """foreground hill height at x — the player rides this line."""
    return FG[0] + FG[1] * math.sin(x * FG[2] + FG[3])


def fresh():
    return {"x": W / 2, "vx": 0.0, "h": 0.0, "vy": 0.0, "t": 0.0, "score": 0.0,
            "over": False, "paused": False, "lives": 3, "maxl": 3, "inv": 0.0,
            "flash": 0.0, "combo": 1, "ct": 0.0, "coins": 0, "shop": False,
            "shoped": 1, "ft": 0.0,
            "up": {k: 0 for k in ("rapid", "twin", "heart", "speed", "magnet")},
            "mt": 0.8, "wt": 6.0, "rt": 2.0, "moons": [], "rings": [],
            "shots": [], "burst": [], "trail": []}


def hit(s, py):
    s["lives"] -= 1
    s["coins"] = max(0, s["coins"] - 10)
    s["inv"], s["flash"], s["combo"] = INV, 1.0, 1
    s["burst"].append({"x": s["x"], "y": py, "r": 6.0, "c": (255, 90, 90)})
    s["moons"] = [m for m in s["moons"]  # no chain deaths on respawn
                  if abs(m["x"] - s["x"]) > 110 or abs(m["y"] - py) > 110]
    if s["lives"] <= 0:
        s["over"] = True


def buy(s, i):
    """shop purchase by slot; True if it went through."""
    if i < 0 or i >= len(SHOP):
        return False
    u = SHOP[i]
    lv = s["up"][u["k"]]
    cost = u["cost"] * (lv + 1)
    if lv >= u["max"] or s["coins"] < cost:
        return False
    s["coins"] -= cost
    s["up"][u["k"]] = lv + 1
    if u["k"] == "heart":
        s["maxl"] += 1
        s["lives"] += 1
    return True


def deadline(s):
    """first wave is short, every wave after it is 30s."""
    return 20 + 30 * (s["shoped"] - 1)


def close_shop(s):
    """a manual visit (shop opened before the deadline) skips no wave."""
    s["shop"] = False
    if s["t"] >= deadline(s):
        s["shoped"] += 1


def shop_text(s):
    out = [f"  WAVE {s['shoped']} CLEARED    coins {int(s['coins'])}  ", ""]
    for i, u in enumerate(SHOP):
        lv = s["up"][u["k"]]
        cost = u["cost"] * (lv + 1)
        cell = ("MAXED" if lv >= u["max"]
                else f"{cost} c" + ("" if s["coins"] >= cost else " (short)"))
        out.append(f" {i + 1}. {u['n']:<13} lv {lv}/{u['max']}   {cell}")
    out += ["", "  1-5 buy     Enter/B resume  "]
    return "\n".join(out)


def step(s, dt, ix=0, jump=False, fire=False):
    """one simulation tick; ix = -1/0/+1, jump/fire request actions.
    returns True once the last life is gone."""
    if s["over"] or s["paused"] or s["shop"]:
        return s["over"]
    s["t"] += dt
    s["score"] += dt * 10
    if s["t"] >= deadline(s):  # wave cleared -> shop
        s["shop"] = True
        return False
    if s["combo"] > 1 and s["t"] - s["ct"] > 4.0:  # ring chain expires
        s["combo"] = 1
    s["inv"] = max(0.0, s["inv"] - dt)
    s["flash"] = max(0.0, s["flash"] - dt * 4)
    s["vx"] += ix * ACC * dt
    if ix == 0:
        s["vx"] *= max(0.0, 1.0 - DRAG * dt)
    mv = MAXV * (1 + 0.15 * s["up"]["speed"])
    s["vx"] = max(-mv, min(mv, s["vx"]))
    s["x"] = max(PR, min(W - PR, s["x"] + s["vx"] * dt))
    if jump and s["h"] <= 0:
        s["vy"] = JUMP
    s["vy"] -= G * dt
    s["h"] = max(0.0, s["h"] + s["vy"] * dt)
    if s["h"] == 0:
        s["vy"] = 0.0
    py, pr = ground(s["x"]) - PR - 1 - s["h"], PR
    s["trail"].append((s["x"], py))
    del s["trail"][:-TRAILN]

    s["ft"] = max(0.0, s["ft"] - dt)
    if fire and s["ft"] == 0:
        s["ft"] = FIRE0 * 0.7 ** s["up"]["rapid"]
        n = 1 + s["up"]["twin"]
        for i in range(n):
            o = i - (n - 1) / 2
            # muzzle at the hip: a shot spawned above center sails over
            # walkers and moons that are already at ground level
            s["shots"].append({"x": s["x"] + o * 6, "y": py + PR,
                               "vx": o * 70, "vy": -SHOT_V})
    for q in s["shots"]:
        q["x"] += q["vx"] * dt
        q["y"] += q["vy"] * dt
    s["shots"] = [q for q in s["shots"] if q["y"] > -8 and not q.get("dead")]

    s["mt"] -= dt
    if s["mt"] <= 0:  # rain gets heavier the longer you last
        s["mt"] = max(0.32, 1.2 - s["t"] * 0.012)
        k = "c" if s["t"] > 20 and _rng.random() < 0.25 else "m"
        m = {"k": k, "x": _rng.uniform(6, W - 6), "y": -14.0,
             "r": _rng.uniform(4, 6) if k == "c" else _rng.uniform(6, 13),
             "vy": _rng.uniform(180, 230) if k == "c"
             else min(150.0, 50.0 + s["t"] * 1.4)}
        if k == "c":
            m["vx"] = _rng.choice((-1, 1)) * _rng.uniform(30, 70)
        s["moons"].append(m)
    s["wt"] -= dt
    if (s["t"] > 8 and s["wt"] <= 0
            and not any(m["k"] == "w" for m in s["moons"])):  # far edge, one
        s["wt"] = max(3.5, 7.0 - s["t"] * 0.03)  # at a time so jumps stay fair
        x = W + 12.0 if s["x"] < W / 2 else -12.0
        s["moons"].append({"k": "w", "x": x, "y": ground(x) - 10,
                           "r": _rng.uniform(8, 11), "vy": 0.0})
    s["rt"] -= dt
    if s["rt"] <= 0:
        s["rt"] = 3.0
        s["rings"].append({"x": _rng.uniform(20, W - 20), "y": -10.0,
                           "r": 7.0, "vy": 45.0})

    for m in s["moons"]:
        k = m["k"]
        if k == "w":
            m["x"] += (32 + s["t"] * 0.28) * (1 if s["x"] > m["x"] else -1) * dt
            m["y"] = ground(m["x"]) - m["r"]
        elif k == "c":
            m["x"] += m["vx"] * dt
        m["y"] += m["vy"] * dt
        for q in s["shots"]:
            if q.get("dead"):
                continue
            dx, dy = q["x"] - m["x"], q["y"] - m["y"]
            if dx * dx + dy * dy < (m["r"] + 4) ** 2:
                q["dead"] = m["dead"] = True
                s["coins"] += B[k]
                s["score"] += 10 * B[k]
                s["burst"].append({"x": m["x"], "y": m["y"], "r": 5.0,
                                   "c": (255, 230, 120)})
                break
        if m.get("dead"):
            continue
        dx, dy = m["x"] - s["x"], m["y"] - py
        d2 = dx * dx + dy * dy
        if d2 < (m["r"] + pr) ** 2:
            if s["inv"] <= 0:
                hit(s, py)
        elif k == "m" and d2 < (m["r"] + pr + 16) ** 2 and not m.get("near"):
            m["near"] = True  # close call pays
            s["score"] += 25 * s["combo"]
            s["burst"].append({"x": m["x"], "y": m["y"], "r": 2.0,
                               "c": (120, 220, 255)})
    s["moons"] = [m for m in s["moons"] if not m.get("dead")
                  and (m["k"] == "w" or m["y"] < ground(m["x"]) - m["r"])]

    mag = s["up"]["magnet"]
    for r in s["rings"]:
        r["y"] += r["vy"] * dt
        if mag:
            r["x"] += (s["x"] - r["x"]) * min(1.0, dt * 1.5 * mag)
        r["pr"] = r["r"] + 1.5 * math.sin(s["t"] * 7 + r["x"])  # pulse
        dx, dy = r["x"] - s["x"], r["y"] - py
        if dx * dx + dy * dy < (r["r"] + pr + 6) ** 2:
            s["score"] += 50 * s["combo"]
            s["coins"] += 6
            s["combo"] = min(5, s["combo"] + 1)
            s["ct"] = s["t"]
            r["dead"] = True
            s["burst"].append({"x": r["x"], "y": r["y"], "r": 4.0})
    s["rings"] = [r for r in s["rings"] if not r.get("dead") and r["y"] < H + 20]

    for b in s["burst"]:
        b["r"] += 130 * dt
    s["burst"] = [b for b in s["burst"] if b["r"] < 46]
    return s["over"]


def draw(s, img):
    img[:] = SKY
    for sx, sy, sr in STARS:
        e.line(img, sx, sy, sx, sy, (210, 210, 255) if sr > 1 else (130, 130, 180))
    e.hill(img, BG[0], BG[1], BG[2], BG[3], (26, 18, 44))
    e.hill(img, FG[0], FG[1], FG[2], FG[3], (44, 32, 64))
    for r in s["rings"]:
        e.ring(img, r["x"], r["y"], r.get("pr", r["r"]), (120, 220, 255))
    for m in s["moons"]:
        if m["k"] == "c":
            e.line(img, m["x"] - m["vx"] * 0.12, m["y"] - m["vy"] * 0.12,
                   m["x"], m["y"], (150, 220, 255), dim=2, wdt=2)
            e.disc(img, m["x"], m["y"], m["r"], (220, 240, 255))
        elif m["k"] == "w":
            e.disc(img, m["x"], m["y"], m["r"], (110, 190, 110))
            e.line(img, m["x"] - 3, m["y"] - 3, m["x"] - 3, m["y"] - 3,
                   (10, 30, 10), wdt=2)
            e.line(img, m["x"] + 3, m["y"] - 3, m["x"] + 3, m["y"] - 3,
                   (10, 30, 10), wdt=2)
        else:
            e.disc(img, m["x"], m["y"], m["r"], (188, 178, 170))
            e.disc(img, m["x"] - m["r"] * 0.3, m["y"] - m["r"] * 0.3,
                   m["r"] * 0.35, (150, 140, 138))
    for q in s["shots"]:
        e.disc(img, q["x"], q["y"], 3, (140, 255, 200))
        e.disc(img, q["x"], q["y"], 6, (80, 255, 180), add=7)
    for i, (tx, ty) in enumerate(reversed(s["trail"])):  # newest = biggest
        e.disc(img, tx, ty, PR - 1 - i * 0.7, (255, 200, 120), add=8)
    if not (s["inv"] > 0 and int(s["t"] * 12) % 2):  # blink while invincible
        py = ground(s["x"]) - PR - 1 - s["h"]
        e.disc(img, s["x"], py, PR + 5, (255, 200, 120), add=5)
        e.disc(img, s["x"], py, PR, (255, 244, 214))
    for b in s["burst"]:
        e.ring(img, b["x"], b["y"], b["r"], b.get("c", (255, 255, 200)), dim=2)
    if s["flash"] > 0.02:  # dark impact blink, C-level translate
        e.fade(img, 0.45 * s["flash"])


def main():
    root = tk.Tk()
    root.title("moonfall")
    root.configure(bg="black")
    root.attributes("-fullscreen", True)
    z = max(2, (root.winfo_screenheight() - 80) // H)
    hud = tk.Label(root, text="", font=("monospace", 11), bg="black",
                   fg="white")
    hud.pack()
    img_label = tk.Label(root, bg="black")
    img_label.pack(expand=True)
    shop_label = tk.Label(root, text="", font=("monospace", 13), bg="#101020",
                          fg="white", justify="left", padx=28, pady=18,
                          relief="groove", bd=3)

    state = fresh()
    held, jump, img = set(), {"go": False}, [None]

    def on_key(ev):
        k = ev.keysym.lower()
        if k == "f11":
            root.attributes("-fullscreen", not root.attributes("-fullscreen"))
        elif k == "escape":
            if root.attributes("-fullscreen"):
                root.attributes("-fullscreen", False)
            else:
                root.destroy()
        elif k == "q":
            root.destroy()
        elif state["shop"]:
            if k in ("1", "2", "3", "4", "5"):
                buy(state, int(k) - 1)
            elif k in ("return", "space", "b"):
                close_shop(state)
        elif k == "p" and not state["over"]:
            state["paused"] = not state["paused"]
        elif k in ("r", "return") and state["over"]:
            state.update(fresh())
        elif k == "b" and not state["over"]:
            state["shop"] = True
        elif k in ("space", "up", "w"):
            jump["go"] = True
        else:
            held.add(k)

    root.bind("<KeyPress>", on_key)
    root.bind("<KeyRelease>", lambda ev: held.discard(ev.keysym.lower()))

    def tick():
        t0 = time.monotonic()
        ix = (("d" in held or "right" in held)
              - ("a" in held or "left" in held))
        j, jump["go"] = jump["go"], False
        step(state, TICK_MS / 1000, ix, j, "k" in held or "x" in held)
        draw(state, _buf := bytearray(W * H * 3))
        e.write_png(TMP, _buf)
        img[0] = tk.PhotoImage(file=TMP).zoom(z, z)
        img_label.configure(image=img[0])
        img_label.image = img[0]  # keep ref
        if state["shop"]:
            shop_label.configure(text=shop_text(state))
            shop_label.place(relx=0.5, rely=0.5, anchor="center")
        else:
            shop_label.place_forget()
        if state["over"]:
            msg = "OUT OF LIVES - R restart, Q quit"
        elif state["shop"]:
            msg = "shop open - 1-5 buy, Enter resume"
        elif state["paused"]:
            msg = "PAUSED - P resume"
        else:
            msg = "move, K shoot, Space jump, B shop, P pause"
        hud.configure(text=f"score={int(state['score'])}  x{state['combo']}  "
                           f"coins={state['coins']}  "
                           f"lives={'*' * state['lives']}  "
                           f"wave={state['shoped']}  {msg}")
        root.after(max(1, int(TICK_MS - (time.monotonic() - t0) * 1000)), tick)

    tick()
    root.mainloop()


if __name__ == "__main__":
    if "--selftest" in sys.argv:  # ponytail: one runnable check for step()
        s = fresh()
        x0 = s["x"]
        step(s, 0.04, 1)
        assert s["x"] > x0 and s["t"] == 0.04 and not s["over"]
        s = fresh()
        step(s, 0.04, 0, jump=True)
        assert s["h"] > 0  # takeoff leaves the ground
        s = fresh()
        s["moons"] = [{"k": "m", "x": s["x"] + 25,
                       "y": ground(s["x"]) - PR - 1, "r": 6, "vy": 0.0}]
        step(s, 0.04, 0)
        assert s["score"] >= 25 and s["burst"]  # near-miss pays
        s = fresh()
        s["rings"] = [{"x": s["x"], "y": ground(s["x"]) - PR - 1, "r": 7,
                       "vy": 0.0}]
        step(s, 0.04, 0)
        assert s["score"] >= 50 and not s["rings"] and s["combo"] == 2
        assert s["coins"] >= 6  # rings fund the shop too
        s = fresh()
        step(s, 0.04, 0, 0, fire=True)
        assert len(s["shots"]) == 1 and s["ft"] > 0  # shot leaves the barrel
        s = fresh()
        py = ground(s["x"]) - PR - 1
        s["shots"] = [{"x": s["x"], "y": py - 30, "vx": 0.0, "vy": -320.0}]
        s["moons"] = [{"k": "m", "x": s["x"], "y": py - 40, "r": 8,
                       "vy": 0.0}]
        step(s, 0.04, 0)
        step(s, 0.04, 0)  # second tick sweeps the spent shot
        assert s["coins"] >= 4 and not s["moons"] and not s["shots"]
        s = fresh()
        s["moons"] = [{"k": "w", "x": s["x"], "y": ground(s["x"]) - 10,
                       "r": 10, "vy": 0.0}]
        step(s, 0.04, 0)
        assert s["lives"] == 2 and s["coins"] == 0  # walker tackle costs a life
        s = fresh()
        s["coins"] = 100
        assert buy(s, 0) and s["up"]["rapid"] == 1 and s["coins"] == 75
        assert buy(s, 2) and s["maxl"] == 4 and s["lives"] == 4
        assert not buy(s, 1)  # twin shot costs 90 now, only 35 left
        s["coins"] = 999
        for _ in range(4):
            buy(s, 0)
        assert s["up"]["rapid"] == 3  # maxed out, further buys refused
        assert "rapid fire" in shop_text(s) and "MAXED" in shop_text(s)
        s = fresh()
        s["t"] = 19.98
        step(s, 0.04, 0)
        assert s["shop"] and not s["over"]  # wave 1 clears at 20s
        close_shop(s)
        assert not s["shop"] and s["shoped"] == 2
        step(s, 0.04, 0)
        assert not s["shop"]  # ...and stays shut until 50s
        s = fresh()
        s["t"] = 10.0
        s["shop"] = True
        close_shop(s)  # popping into the shop by hand banks no wave
        assert s["shoped"] == 1
        s = fresh()
        s["lives"] = 1
        s["moons"] = [{"k": "m", "x": s["x"], "y": ground(s["x"]) - PR - 1,
                       "r": 9, "vy": 0.0}]
        assert step(s, 0.04, 0) is True  # last life on your head ends it
        assert s["lives"] == 0 and s["inv"] > 0
        s = fresh()
        s["over"] = True
        x0 = s["x"]
        step(s, 0.04, 1)
        assert s["x"] == x0  # frozen once over
        img = bytearray(W * H * 3)
        draw(fresh(), img)
        assert len(img) == W * H * 3 and sum(img) > 0
        print("selftest ok")
    else:
        main()
