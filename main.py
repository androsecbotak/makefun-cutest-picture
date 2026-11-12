#!/usr/bin/env python3
"""Make the cutest picture — make.fun bounty entry.

A deterministic, standard-library-only Python program that draws one
cute picture (a chubby kitten) and writes it to /output/entry.png.

No network, no randomness, no third-party libraries: the PNG encoder
is written by hand on top of zlib (stdlib). Two runs produce
byte-identical output.
"""

import math
import os
import struct
import zlib

# ---------------------------------------------------------------------------
# Canvas (rendered at 2x, then box-downsampled for smooth edges)
# ---------------------------------------------------------------------------
SS = 2                      # supersampling factor
W, H = 1024, 1024           # final size
RW, RH = W * SS, H * SS     # render size


class Canvas:
    def __init__(self):
        self.buf = bytearray(RW * RH * 3)

    def _set(self, x, y, r, g, b):
        if 0 <= x < RW and 0 <= y < RH:
            i = (y * RW + x) * 3
            self.buf[i] = r
            self.buf[i + 1] = g
            self.buf[i + 2] = b

    def _blend(self, x, y, r, g, b, a):
        """Alpha-blend a colour over the pixel at (x, y). a in [0, 1]."""
        if a <= 0 or not (0 <= x < RW and 0 <= y < RH):
            return
        i = (y * RW + x) * 3
        if a >= 1:
            self.buf[i] = r
            self.buf[i + 1] = g
            self.buf[i + 2] = b
            return
        self.buf[i] = int(self.buf[i] * (1 - a) + r * a)
        self.buf[i + 1] = int(self.buf[i + 1] * (1 - a) + g * a)
        self.buf[i + 2] = int(self.buf[i + 2] * (1 - a) + b * a)

    def row_fill(self, y, x0, x1, col):
        """Fill pixels x0..x1 (float bounds) on row y, solid colour."""
        if y < 0 or y >= RH:
            return
        a = max(0, int(math.floor(x0)))
        b = min(RW - 1, int(math.ceil(x1)) - 1)
        if b < a:
            return
        r, g, bl = col
        base = (y * RW + a) * 3
        n = b - a + 1
        self.buf[base:base + n * 3] = bytes((r, g, bl)) * n

    def circle(self, cx, cy, rad, col, alpha=1.0):
        cx *= SS
        cy *= SS
        rad *= SS
        y0 = max(0, int(math.floor(cy - rad)))
        y1 = min(RH - 1, int(math.ceil(cy + rad)))
        for y in range(y0, y1 + 1):
            dy = (y + 0.5) - cy
            if abs(dy) >= rad:
                continue
            dx = math.sqrt(rad * rad - dy * dy)
            if alpha >= 1.0:
                self.row_fill(y, cx - dx, cx + dx, col)
            else:
                for x in range(max(0, int(cx - dx)), min(RW - 1, int(cx + dx)) + 1):
                    self._blend(x, y, col[0], col[1], col[2], alpha)

    def ellipse(self, cx, cy, rx, ry, col, alpha=1.0):
        cx *= SS
        cy *= SS
        rx *= SS
        ry *= SS
        y0 = max(0, int(math.floor(cy - ry)))
        y1 = min(RH - 1, int(math.ceil(cy + ry)))
        for y in range(y0, y1 + 1):
            dy = (y + 0.5) - cy
            if abs(dy) >= ry:
                continue
            t = 1.0 - (dy * dy) / (ry * ry)
            dx = rx * math.sqrt(max(0.0, t))
            if alpha >= 1.0:
                self.row_fill(y, cx - dx, cx + dx, col)
            else:
                for x in range(max(0, int(cx - dx)), min(RW - 1, int(cx + dx)) + 1):
                    self._blend(x, y, col[0], col[1], col[2], alpha)

    def poly(self, pts, col):
        """Scanline-fill a polygon given as [(x, y), ...] in final coords."""
        pts = [(x * SS, y * SS) for x, y in pts]
        ys = [p[1] for p in pts]
        y0 = max(0, int(math.floor(min(ys))))
        y1 = min(RH - 1, int(math.ceil(max(ys))))
        n = len(pts)
        for y in range(y0, y1 + 1):
            yc = y + 0.5
            xs = []
            for i in range(n):
                x1, y1p = pts[i]
                x2, y2p = pts[(i + 1) % n]
                if (y1p <= yc < y2p) or (y2p <= yc < y1p):
                    t = (yc - y1p) / (y2p - y1p)
                    xs.append(x1 + t * (x2 - x1))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                self.row_fill(y, xs[k], xs[k + 1], col)

    def thick_line(self, x1, y1, x2, y2, w, col):
        """Draw a thick line segment (final coords, width in final px).

        NOTE: poly() does the SS scaling itself, so pass final coords here.
        """
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length == 0:
            return
        nx, ny = -dy / length, dx / length
        hw = w / 2.0
        self.poly([
            (x1 + nx * hw, y1 + ny * hw),
            (x2 + nx * hw, y2 + ny * hw),
            (x2 - nx * hw, y2 - ny * hw),
            (x1 - nx * hw, y1 - ny * hw),
        ], col)

    def tube(self, pts, w, col):
        """Draw a smooth tube along a polyline (overlapping circles, so
        there are no seams at the joints). Final coords."""
        r = w / 2.0
        for (x, y) in pts:
            self.circle(x, y, r, col)

    def arc(self, cx, cy, rad, a0, a1, w, col, steps=48):
        """Draw a thick arc (angles in radians, final coords)."""
        pts = []
        for i in range(steps + 1):
            a = a0 + (a1 - a0) * i / steps
            pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
        for i in range(len(pts) - 1):
            self.thick_line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], w, col)

    def vgrad(self, top, bottom):
        """Vertical gradient background (final coords)."""
        for y in range(RH):
            t = y / max(1, RH - 1)
            r = int(top[0] + (bottom[0] - top[0]) * t)
            g = int(top[1] + (bottom[1] - top[1]) * t)
            b = int(top[2] + (bottom[2] - top[2]) * t)
            base = y * RW * 3
            self.buf[base:base + RW * 3] = bytes((r, g, b)) * RW

    def downsample(self):
        """Box-average the 2x buffer down to W x H, returns bytes."""
        out = bytearray(W * H * 3)
        src = self.buf
        for y in range(H):
            sy = y * SS
            for x in range(W):
                sx = x * SS
                r = g = b = 0
                for dy in range(SS):
                    base = ((sy + dy) * RW + sx) * 3
                    for dx in range(SS):
                        i = base + dx * 3
                        r += src[i]
                        g += src[i + 1]
                        b += src[i + 2]
                o = (y * W + x) * 3
                n = SS * SS
                out[o] = r // n
                out[o + 1] = g // n
                out[o + 2] = b // n
        return bytes(out)


# ---------------------------------------------------------------------------
# Minimal PNG encoder (RGB, 8-bit, filter 0, zlib)
# ---------------------------------------------------------------------------
def write_png(path, rgb, w, h):
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]

    def chunk(ctype, data):
        c = struct.pack(">I", len(data)) + ctype + data
        c += struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)
        return c

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


# ---------------------------------------------------------------------------
# The picture: a chubby kitten with big glossy eyes, head tilted, tiny bow
# ---------------------------------------------------------------------------
CREAM = (255, 243, 224)   # fur
CREAM_D = (244, 224, 196)  # fur shading
OUTLINE = (214, 164, 120)  # soft warm outline
PINK = (255, 183, 197)     # inner ear / nose / blush
PINK_D = (244, 143, 168)   # bow
BROWN = (92, 64, 48)       # eyes / mouth
IRIS = (122, 84, 52)
WHITE = (255, 255, 255)
GRAY = (176, 164, 158)     # whiskers
BELLY = (255, 250, 240)


def rot(px, py, cx, cy, ang):
    """Rotate point (px, py) around (cx, cy) by ang radians."""
    c, s = math.cos(ang), math.sin(ang)
    dx, dy = px - cx, py - cy
    return (cx + dx * c - dy * s, cy + dx * s + dy * c)


def draw():
    c = Canvas()
    # Soft pastel sky: peachy pink up top, warm cream below.
    c.vgrad((255, 228, 236), (255, 246, 232))

    # Scattered soft decorations: tiny hearts and dots, low contrast.
    deco = [
        (120, 130, 10, (255, 205, 218)), (900, 110, 12, (255, 205, 218)),
        (180, 880, 11, (255, 214, 224)), (860, 880, 10, (255, 214, 224)),
        (70, 480, 8, (255, 222, 230)), (950, 500, 9, (255, 222, 230)),
        (300, 90, 7, (255, 205, 218)), (700, 70, 8, (255, 205, 218)),
    ]
    for x, y, r, col in deco:
        c.circle(x, y, r, col)

    # Head geometry (tilted -6 degrees around the head centre).
    HX, HY, HR = 512, 470, 300
    TILT = math.radians(-6)

    def rp(px, py):
        return rot(px, py, HX, HY, TILT)

    # Tail: curled, peeking out on the right, behind the body.
    tail_pts = []
    for i in range(61):
        a = math.radians(-140) + (math.radians(55) - math.radians(-140)) * i / 60
        tail_pts.append((790 + 120 * math.cos(a), 830 + 120 * math.sin(a)))
    c.tube(tail_pts, 46, CREAM_D)
    c.circle(tail_pts[-1][0], tail_pts[-1][1], 23, CREAM_D)

    # Body: chubby ellipse + lighter belly, with a soft outline so it
    # does not melt into the background.
    c.ellipse(512, 872, 232, 144, OUTLINE)
    c.ellipse(512, 872, 225, 138, CREAM)
    c.ellipse(512, 892, 150, 92, BELLY)

    # Paws: two small rounded paws at the bottom of the body.
    c.ellipse(420, 968, 62, 42, CREAM)
    c.ellipse(604, 968, 62, 42, CREAM)
    for px in (396, 420, 444):
        c.circle(px, 952, 5, CREAM_D)
    for px in (580, 604, 628):
        c.circle(px, 952, 5, CREAM_D)

    # Ears (outer cream triangles, inner pink), rotated with the head.
    # Tips sit well above the head circle (head top is y=170) so the
    # ears clearly stick out; bases are hidden behind the head.
    for ex, sgn in ((322, -1), (702, 1)):
        tip = rp(ex + 30 * sgn, 118)
        base1 = rp(ex - 86 * sgn, 330)
        base2 = rp(ex + 82 * sgn, 318)
        c.poly([tip, base1, base2], CREAM)
        itip = rp(ex + 24 * sgn, 168)
        ibase1 = rp(ex - 48 * sgn, 312)
        ibase2 = rp(ex + 46 * sgn, 304)
        c.poly([itip, ibase1, ibase2], PINK)

    # Head: soft outline ring, then the face.
    c.circle(HX, HY, HR + 6, OUTLINE)
    c.circle(HX, HY, HR, CREAM)

    # Eyes: big, glossy, slightly different heights from the tilt.
    for ex in (392, 632):
        exr, eyr = rp(ex, 440)
        c.ellipse(exr, eyr, 74, 82, WHITE)
        c.circle(exr, eyr + 4, 52, IRIS)
        c.circle(exr, eyr + 4, 30, BROWN)
        c.circle(exr - 18, eyr - 22, 18, WHITE)   # big sparkle
        c.circle(exr + 20, eyr + 18, 8, WHITE)    # small sparkle

    # Blush: soft pink ovals on the cheeks.
    for bx in (330, 694):
        bxr, byr = rp(bx, 560)
        c.ellipse(bxr, byr, 52, 30, PINK, alpha=0.55)

    # Nose: tiny pink rounded triangle.
    nx, ny = rp(512, 545)
    c.poly([(nx - 26, ny - 8), (nx + 26, ny - 8), (nx, ny + 22)], PINK_D)
    c.circle(nx, ny + 4, 12, PINK_D)

    # Mouth: small "w" curve under the nose.
    c.arc(nx - 16, ny + 34, 16, math.radians(15), math.radians(165), 5, BROWN)
    c.arc(nx + 16, ny + 34, 16, math.radians(15), math.radians(165), 5, BROWN)

    # Whiskers: three thin lines per side.
    for sgn in (-1, 1):
        wx, wy = rp(512 + 150 * sgn, 545)
        for dy, tilt in ((-18, -14), (0, -2), (18, 12)):
            c.thick_line(wx, wy + dy,
                         wx + 108 * sgn, wy + dy + tilt, 4, GRAY)

    # Bow on the right ear: two triangles + centre knot.
    bx, by = rp(706, 218)
    c.poly([(bx - 52, by - 26), (bx - 52, by + 26), (bx - 8, by)], PINK_D)
    c.poly([(bx + 52, by - 26), (bx + 52, by + 26), (bx + 8, by)], PINK_D)
    c.circle(bx, by, 13, (226, 110, 140))

    # A few sparkles near the head.
    for sx, sy in ((250, 250), (790, 210), (850, 620), (170, 640)):
        c.circle(sx, sy, 4, (255, 255, 255))
        c.circle(sx, sy, 2, (255, 213, 128))

    return c.downsample()


def main():
    out = "/output/entry.png" if os.path.isdir("/output") else "output/entry.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    rgb = draw()
    write_png(out, rgb, W, H)
    print("wrote", out, len(rgb), "bytes of RGB,", os.path.getsize(out), "bytes PNG")


if __name__ == "__main__":
    main()
