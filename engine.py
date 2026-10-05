"""Shared 2D engine: pixel ops, PNG output, captions, mux. Pure stdlib + ffmpeg.
Films import this and keep only their story beats; `python3 film.py --mux
out.mp4` renders frames, writes the caption filter with a resolved font,
and muxes with 2d/audio.wav in one command.

Ops: sky() gradient bands, hill() sine silhouettes, disc() filled/glow,
ring() outlines, line() thin/thick, fade(), write_png(), Frames() counter,
save_caps() drawtext filters, mux() ffmpeg. Hot loops are C-level fills
(bytes.translate, per-chord/row slices) — any rewrite must stay
pixel-identical (old-vs-new benchmark + fuzz, then cmp-identical rebuild).
"""
import math
import os
import shutil
import struct
import subprocess
import zlib

W, H, FPS = 480, 270, 10
AUDIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'audio.wav')

FONT_CANDIDATES = [
    '/usr/share/fonts/liberation-sans-fonts/LiberationSans-Regular.ttf',  # Fedora
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',  # Debian/Ubuntu
    '/usr/share/fonts/truetype/liberation-sans-fonts/LiberationSans-Regular.ttf',  # legacy
]

_font = None


def find_font():
    global _font
    if _font is None:
        for p in FONT_CANDIDATES:
            if os.path.exists(p):
                _font = p
                break
        else:
            raise FileNotFoundError('no Liberation Sans TTF found; tried: '
                                    + ', '.join(FONT_CANDIDATES))
    return _font


def lerp(a, b, t):
    t = t * t * (3 - 2 * t)
    return a + (b - a) * t


def lerp3(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def write_png(path, img):
    rows = [b'\x00' + bytes(img[y * W * 3:(y + 1) * W * 3]) for y in range(H)]
    raw = b''.join(rows)

    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n'
                + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw, 3)) + chunk(b'IEND', b''))


def sky(stops):
    """Vertical gradient; stops = [(pos 0-1, (r,g,b)), ...]."""
    img = bytearray(W * H * 3)
    for y in range(H):
        p = y / (H - 1)
        for k in range(len(stops) - 1):
            if stops[k][0] <= p <= stops[k + 1][0]:
                span = stops[k + 1][0] - stops[k][0] or 1
                t = (p - stops[k][0]) / span
                r, g, b = lerp3(stops[k][1], stops[k + 1][1], t)
                break
        img[y * W * 3:(y + 1) * W * 3] = bytes((r, g, b)) * W
    return img


def hill(img, base, amp, fr, ph, col):
    ys = [int(base + amp * math.sin(x * fr + ph)) for x in range(W)]
    top, bot = max(0, min(ys)), min(H, max(ys))
    full = bytes(col) * W  # rows below the lowest dip are solid: one C fill each
    for y in range(bot, H):
        img[y * W * 3:(y + 1) * W * 3] = full
    c3 = bytes(col)  # the wavy band stays per-pixel but is only ~2*amp rows
    for y in range(top, bot):
        o = y * W * 3
        for x in range(W):
            if ys[x] <= y:
                img[o + x * 3:o + x * 3 + 3] = c3


def disc(img, cx, cy, r, rgb, add=0):
    """Filled disc; add=N adds rgb//N instead of overwriting (glow)."""
    if add:  # chord scan + hoisted constants: no condition, no // per pixel
        kr, kg, kb = rgb[0] // add, rgb[1] // add, rgb[2] // add
        if kr == 0 and kg == 0 and kb == 0:
            return
        _min = min
        for yy in range(max(0, int(cy - r)), min(H, int(cy + r) + 1)):
            s = math.sqrt(max(0.0, r * r - (yy - cy) ** 2))
            a = max(0, int(math.ceil(cx - s)))
            b = min(W, int(math.floor(cx + s)) + 1)
            for o in range((yy * W + a) * 3, (yy * W + b) * 3, 3):
                img[o] = _min(255, img[o] + kr)
                img[o + 1] = _min(255, img[o + 1] + kg)
                img[o + 2] = _min(255, img[o + 2] + kb)
        return
    for yy in range(max(0, int(cy - r)), min(H, int(cy + r) + 1)):
        s = math.sqrt(max(0.0, r * r - (yy - cy) ** 2))
        a = max(0, int(math.ceil(cx - s)))
        b = min(W, int(math.floor(cx + s)) + 1)
        if b > a:  # whole chord in one C-level slice fill
            img[(yy * W + a) * 3:(yy * W + a) * 3 + (b - a) * 3] = bytes(rgb) * (b - a)


def ring(img, rx, ry, rr, rgb, dim=2):
    """Thin expanding ring outline, additive."""
    kr, kg, kb = rgb[0] // dim, rgb[1] // dim, rgb[2] // dim
    _min, _hypot = min, math.hypot
    for yy in range(max(0, int(ry - rr) - 3), min(H, int(ry + rr) + 4)):
        for xx in range(max(0, int(rx - rr) - 3), min(W, int(rx + rr) + 4)):
            if abs(_hypot(xx - rx, yy - ry) - rr) < 2.5:
                o = (yy * W + xx) * 3
                img[o] = _min(255, img[o] + kr)
                img[o + 1] = _min(255, img[o + 1] + kg)
                img[o + 2] = _min(255, img[o + 2] + kb)


def line(img, x0, y0, x1, y1, rgb, dim=1, wdt=1):
    """dim=1 overwrites, dim=N adds rgb//N; wdt=2 draws thick."""
    n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    last = max(1, n - 1)
    if dim == 1 and wdt == 1:  # hot path (rain, branches): no per-pixel branch
        c3 = bytes(rgb)
        for i in range(n):
            t = i / last
            x, y = int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t)
            if 0 <= x < W and 0 <= y < H:
                o = (y * W + x) * 3
                img[o:o + 3] = c3
        return
    kr, kg, kb = rgb[0] // dim, rgb[1] // dim, rgb[2] // dim
    _min = min
    for i in range(n):
        t = i / last
        x, y = int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t)
        for wy in range(-wdt + 1, wdt):
            for wx in range(-wdt + 1, wdt):
                xx, yy = x + wx, y + wy
                if 0 <= xx < W and 0 <= yy < H:
                    o = (yy * W + xx) * 3
                    if dim == 1:
                        img[o], img[o + 1], img[o + 2] = rgb
                    else:
                        img[o] = _min(255, img[o] + kr)
                        img[o + 1] = _min(255, img[o + 1] + kg)
                        img[o + 2] = _min(255, img[o + 2] + kb)


def fade(img, f):
    img[:] = img.translate(bytes(int(v * (1 - f)) for v in range(256)))


class Frames:
    """Numbered-frame writer: push(img) saves and returns frame count."""

    def __init__(self, pattern):
        self.pattern = pattern
        self.n = 0

    def push(self, img):
        f = self.pattern % self.n
        self.n += 1
        write_png(f, img)
        return self.n


def save_caps(path, entries, fontsize=22):
    """entries = [(text, t0, t1), ...] -> ffmpeg filter_script file."""
    font = find_font()
    parts = []
    for text, a, b in entries:
        text = text.replace("'", '').replace(':', '')
        parts.append(
            f"drawtext=fontfile={font}:text='{text}':fontcolor=white:"
            f"fontsize={fontsize}:x=(w-text_w)/2:y=h-40:enable='between(t,{a},{b})'")
    with open(path, 'w') as f:
        f.write(','.join(parts))


def mux(pattern, caps_file, out, audio=AUDIO, fps=FPS):
    if shutil.which('ffmpeg') is None:
        raise FileNotFoundError('ffmpeg not found on PATH')
    if not os.path.exists(audio):
        raise FileNotFoundError(f'audio not found: {audio} (run audio.py first)')
    subprocess.run(['ffmpeg', '-y', '-framerate', str(fps), '-i', pattern,
                    '-i', audio, '-filter_script:v', caps_file,
                    '-pix_fmt', 'yuv420p', '-shortest', '-c:a', 'aac', out],
                   check=True)
    print('wrote', out)


if __name__ == '__main__':  # ponytail: one runnable check for the shared ops
    find_font()
    assert lerp(0, 10, 0.5) == 5.0 and lerp3((0, 0, 0), (10, 20, 30), 1) == (10, 20, 30)
    img = sky([(0, (0, 0, 0)), (1, (255, 255, 255))])
    assert len(img) == W * H * 3 and img[0] == 0 and img[-1] == 255
    hill(img, H // 2, 0, 0.02, 0, (9, 9, 9))
    line(img, 0, 0, 10, 0, (4, 5, 6))
    ring(img, 20, 20, 8, (7, 8, 9))
    fade(img, 1.0)
    assert sum(img) == 0
    write_png('_selftest.png', img)
    os.remove('_selftest.png')
    print('selftest ok')
