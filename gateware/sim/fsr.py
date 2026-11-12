#!/usr/bin/env python3
"""fsr.py: the scaler: AMD's FSR 1 edge adaptive spatial upsampling (EASU: ffx_fsr1.h FsrEasuF, MIT
licence), 720 x 480 to 1440 x 1080, as the hardware does it, and as the shader does for comparison.

The shader, per output pixel: the 12 source pixels round it; from their luma an edge direction and
an "edge-ness" (len), interpolated between the four nearest pixels' own; a Lanczos-like kernel
rotated along the edge and stretched by len weighs the 12; the result held between the least and
greatest of the four nearest.

The hardware (rtl/easu.v, rtl/easu_ana.v):
- each source pixel's own part of the direction and len is worked out once, as the pixels stream by
  (analysis(): dx, dy the luma differences across it, ls = lenX^2 + lenY^2 in 64ths);
- the output's place between source pixels takes 2 x 9 values (1440/720 = 2, 1080/480 = 9/4): the
  four pixels' parts are weighed by whole numbers (72nds);
- the direction is put in one of 32 bins over the half turn, len in one of 8, and the 12 weights
  for (place, direction, len) come from a table (table(): 4608 entries, the weights in 256ths,
  their sum 256: the division by the weights' sum is in the table).

    fsr.py table OUT                # the table for $readmemh: OUT0.hex to OUT3.hex, three weights
                                    # of 10 bits a line each
    fsr.py picture IN.png OUT.png [float|nearest]     # a 720 x 480 picture scaled, as the hardware
                                                      # (default), the shader, or by the nearest pixel
"""
import math
import sys

TAPS = [(0, -1), (1, -1), (-1, 0), (0, 0), (1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (2, 1), (0, 2), (1, 2)]
NANG, NLEN = 32, 8
PX = [0.75, 0.25]                                   # an output column's place between two source ones
TAN = [round(1024 * math.tan((2 * k - 1) * math.pi / 64)) for k in range(1, 9)]    # the bins' edges, to 45 degrees
LEN_TH = [-(-(2 * j - 1) * 9216 // 14) for j in range(1, 8)]                      # len's levels' edges
RECIP = [0] + [4096 // v for v in range(1, 256)]


def phase_y(oy):
    """an output row: (the source row above its place, the place below it in 18ths)"""
    return (8 * oy - 5) // 18, (8 * oy - 5) % 18


def phase_x(ox):
    return (2 * ox - 1) // 4, PX[ox & 1]


def kernel(ppx, ppy, dx, dy, ln):
    """the 12 weights, as the shader after its direction (dx, dy: a unit vector) and len (0-1) are
    known"""
    ln = ln * ln
    stretch = (dx * dx + dy * dy) / max(abs(dx), abs(dy))
    len2x, len2y = 1 + (stretch - 1) * ln, 1 - 0.5 * ln
    lob = 0.5 + ((1 / 4 - 0.04) - 0.5) * ln
    clp = 1 / lob
    ws = []
    for tx, ty in TAPS:
        ox, oy = tx - ppx, ty - ppy
        vx, vy = (ox * dx + oy * dy) * len2x, (ox * -dy + oy * dx) * len2y
        d2 = min(vx * vx + vy * vy, clp)
        wb, wa = 2 / 5 * d2 - 1, lob * d2 - 1
        ws.append((25 / 16 * wb * wb - (25 / 16 - 1)) * wa * wa)
    return ws


def table():
    """[py 0-8][px 0-1][ang][len]: 12 weights in 256ths, their sum 256; py: the place below the
    row above in 18ths is 2 py + 1"""
    out = {}
    for py in range(9):
        for px in range(2):
            for ang in range(NANG):
                th = ang * math.pi / NANG
                for li in range(NLEN):
                    ws = kernel(PX[px], (2 * py + 1) / 18, math.cos(th), math.sin(th), li / (NLEN - 1))
                    tot = sum(ws)
                    q = [round(w / tot * 256) for w in ws]
                    q[max(range(12), key=lambda k: q[k])] += 256 - sum(q)
                    out[py, px, ang, li] = q
    return out


def analysis(luma, w, h):
    """each source pixel's (dx, dy, ls): rtl/easu_ana.v.  luma: h rows of w"""
    def part(lo, mid, hi):
        d = hi - lo
        mx = max(abs(hi - mid), abs(mid - lo))
        t = min(64, (abs(d) * RECIP[mx]) >> 6)
        return d, (t * t) >> 6
    out = []
    for y in range(h):
        up, dn = luma[max(y - 1, 0)], luma[min(y + 1, h - 1)]
        row = luma[y]
        line = []
        for x in range(w):
            dx, sx = part(row[max(x - 1, 0)], row[x], row[min(x + 1, w - 1)])
            dy, sy = part(up[x], row[x], dn[x])
            line.append((dx, dy, sx + sy))
        out.append(line)
    return out


def angle_bin(ax, ay):
    """the direction's bin, 0-31 over the half turn, by comparisons (the direction and its opposite
    are one)"""
    if ax == 0 and ay == 0:
        return 0
    m, n = (abs(ax), abs(ay)) if abs(ax) >= abs(ay) else (abs(ay), abs(ax))
    t = sum(1 for k in TAN if n * 1024 >= m * k)
    if abs(ay) > abs(ax):
        t = 16 - t
    if (ax < 0) != (ay < 0) and ax != 0 and ay != 0:
        t = (32 - t) % 32
    return t % 32


def scale_hw(pix, ana, w, h, tab):
    """rtl/easu.v: pix h rows of w (y, cb, cr) -> 1080 rows of 1440"""
    out = []
    cx = lambda x: min(max(x, 0), w - 1)
    cy = lambda y: min(max(y, 0), h - 1)
    for oy in range(h * 9 // 4):
        fy, ky = phase_y(oy)
        wy = (18 - ky, ky)
        rows = [pix[cy(fy + d)] for d in (-1, 0, 1, 2)]
        arow = [ana[cy(fy)], ana[cy(fy + 1)]]
        line = []
        for ox in range(w * 2):
            fx = (2 * ox - 1) // 4
            px = ox & 1
            wx = (1, 3) if px == 0 else (3, 1)
            ax = ay = al = 0
            for j in range(2):
                for i in range(2):
                    a = arow[j][cx(fx + i)]
                    wgt = wx[i] * wy[j]
                    ax += wgt * a[0]
                    ay += wgt * a[1]
                    al += wgt * a[2]
            ang = angle_bin(ax, ay)
            li = sum(1 for t in LEN_TH if al >= t)
            wts = tab[(ky - 1) // 2, px, ang, li]
            taps = [rows[ty + 1][cx(fx + tx)] for tx, ty in TAPS]
            near = [taps[3], taps[4], taps[7], taps[8]]
            p = []
            for c in range(3):
                v = (sum(wt * t[c] for wt, t in zip(wts, taps)) + 128) >> 8
                p.append(min(max(n[c] for n in near), max(min(n[c] for n in near), v)))
            line.append(tuple(p))
        out.append(line)
    return out


def scale_float(pix, w, h):
    """the shader, on the same pixels (luma = y)"""
    out = []
    cx = lambda x: min(max(x, 0), w - 1)
    cy = lambda y: min(max(y, 0), h - 1)
    L = lambda x, y: pix[cy(y)][cx(x)][0] / 255.0
    for oy in range(h * 9 // 4):
        sy = (oy + 0.5) * 4 / 9 - 0.5
        fy = math.floor(sy)
        ppy = sy - fy
        line = []
        for ox in range(w * 2):
            sx = (ox + 0.5) / 2 - 0.5
            fx = math.floor(sx)
            ppx = sx - fx
            dx = dy = ln = 0.0
            for (i, j, wgt) in ((0, 0, (1 - ppx) * (1 - ppy)), (1, 0, ppx * (1 - ppy)), (0, 1, (1 - ppx) * ppy), (1, 1, ppx * ppy)):
                x, y = fx + i, fy + j
                a, b, c, d, e = L(x, y - 1), L(x - 1, y), L(x, y), L(x + 1, y), L(x, y + 1)
                m = max(abs(d - c), abs(c - b))
                dirx = d - b
                dx += dirx * wgt
                lx = min(1.0, abs(dirx) / m) if m else 0.0
                ln += lx * lx * wgt
                m = max(abs(e - c), abs(c - a))
                diry = e - a
                dy += diry * wgt
                ly = min(1.0, abs(diry) / m) if m else 0.0
                ln += ly * ly * wgt
            r = dx * dx + dy * dy
            if r < 1 / 32768:
                dx, dy = 1.0, 0.0
            else:
                r = 1 / math.sqrt(r)
                dx, dy = dx * r, dy * r
            ws = kernel(ppx, ppy, dx, dy, ln * 0.5)
            taps = [pix[cy(fy + ty)][cx(fx + tx)] for tx, ty in TAPS]
            near = [taps[3], taps[4], taps[7], taps[8]]
            tot = sum(ws)
            p = []
            for c in range(3):
                v = sum(wt * t[c] for wt, t in zip(ws, taps)) / tot
                p.append(int(min(max(n[c] for n in near), max(min(n[c] for n in near), round(v)))))
            line.append(tuple(p))
        out.append(line)
    return out


def scale_nearest(pix, w, h):
    return [[pix[(4 * oy + 2) // 9][ox >> 1] for ox in range(2 * w)] for oy in range(h * 9 // 4)]


def to_ycc(rgb):
    r, g, b = rgb
    return (max(0, min(255, (66 * r + 129 * g + 25 * b + 128 >> 8) + 16)),
            max(0, min(255, (-38 * r - 74 * g + 112 * b + 128 >> 8) + 128)),
            max(0, min(255, (112 * r - 94 * g - 18 * b + 128 >> 8) + 128)))


def to_rgb(p):
    clamp = lambda v: 0 if v < 0 else 255 if v > 0xFFFF else v >> 8
    y, cb, cr = p
    yy = 298 * max(y - 16, 0)
    return (clamp(yy + 409 * (cr - 128) + 128), clamp(yy - 100 * (cb - 128) - 208 * (cr - 128) + 128),
            clamp(yy + 516 * (cb - 128) + 128))


def main():
    a = sys.argv[1:]
    if a[0] == "table":
        tab = table()
        # four files, three weights each (rtl/easu.v's four ROMs): OUT0.hex ... OUT3.hex
        fs = [open("%s%d.hex" % (a[1][:-4] if a[1].endswith(".hex") else a[1], k), "w") for k in range(4)]
        for py in range(16):
            for px in range(2):
                for ang in range(NANG):
                    for li in range(NLEN):
                        q = tab.get((py, px, ang, li), [0] * 12)
                        for k in range(4):
                            fs[k].write("%08x\n" % sum((v & 0x3FF) << 10 * j for j, v in enumerate(q[3 * k:3 * k + 3])))
        for f in fs:
            f.close()
        lo = min(min(q) for q in tab.values())
        hi = max(max(q) for q in tab.values())
        print("table: %d entries, weights %d..%d" % (len(tab), lo, hi))
    elif a[0] == "picture":
        from PIL import Image
        im = Image.open(a[1]).convert("RGB")
        w, h = im.size
        pix = [[to_ycc(im.getpixel((x, y))) for x in range(w)] for y in range(h)]
        how = a[3] if len(a) > 3 else "hw"
        if how == "float":
            out = scale_float(pix, w, h)
        elif how == "nearest":
            out = scale_nearest(pix, w, h)
        else:
            out = scale_hw(pix, analysis([[p[0] for p in row] for row in pix], w, h), w, h, table())
        res = Image.new("RGB", (2 * w, h * 9 // 4))
        res.putdata([to_rgb(p) for row in out for p in row])
        res.save(a[2])


if __name__ == "__main__":
    main()
